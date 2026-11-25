// SPDX-License-Identifier: MIT
#include "planner.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <random>
#include <span>
#include <stdexcept>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using transfer::Cost;
using transfer::Problem;
using transfer::Range;
using transfer::Strategy;

constexpr std::uint32_t kib = 1024;
constexpr std::uint32_t extent_bytes = 2 * kib * kib;
constexpr std::array<std::uint32_t, 4> caps_bytes{4 * kib, 16 * kib, 64 * kib, extent_bytes};
constexpr std::array strategies{Strategy::exact, Strategy::greedy, Strategy::optimal};
constexpr std::array names{"exact", "greedy", "optimal"};

struct Options {
    std::uint32_t unit_bytes = 64;
    std::uint32_t samples = 31;
    std::uint32_t seed = 987651;
};

Options parse(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 == argc) {
            throw std::invalid_argument("expected a value after each option");
        }
        const std::string_view name(argv[index]);
        const std::string_view value(argv[index + 1]);
        std::uint32_t parsed = 0;
        const auto [end, error] = std::from_chars(value.begin(), value.end(), parsed);
        if (error != std::errc{} || end != value.end()) {
            throw std::invalid_argument("expected an unsigned integer");
        }
        if (name == "--unit-bytes") {
            options.unit_bytes = parsed;
        } else if (name == "--samples") {
            options.samples = parsed;
        } else if (name == "--seed") {
            options.seed = parsed;
        } else {
            throw std::invalid_argument("unknown option");
        }
    }
    const auto unit = options.unit_bytes;
    if (unit < 16 || unit > 1024 || (unit & (unit - 1)) != 0) {
        throw std::invalid_argument("unit-bytes must be a power of two in [16, 1024]");
    }
    if (options.samples < 9 || options.samples > 201) {
        throw std::invalid_argument("samples must be in [9, 201]");
    }
    return options;
}

double elapsed_ns(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::nano>(b - a).count();
}

double percentile(std::vector<double> values, unsigned percent) {
    std::sort(values.begin(), values.end());
    const auto rank = ((values.size() - 1) * percent + 50) / 100;
    return values[rank];
}

struct Buffers {
    std::vector<std::uint8_t> source;
    std::vector<std::uint8_t> staging;
    std::vector<std::uint8_t> destination;

    explicit Buffers(std::size_t bytes)
        : source(bytes), staging(bytes), destination(bytes) {}
};

void replay(std::span<const Range> ops, std::size_t unit_bytes, Buffers& b) {
    std::size_t slot = 0;
    for (const auto range : ops) {
        const auto size = (range.end - range.begin) * unit_bytes;
        std::memcpy(b.staging.data() + slot, b.source.data() + range.begin * unit_bytes, size);
        slot += size;
    }
    // All host staging completes before one simulated batch consumes the arena.
    // This is a compiler timing boundary, with no hardware queue/fence cost.
    std::atomic_signal_fence(std::memory_order_seq_cst);
    slot = 0;
    for (const auto range : ops) {
        const auto size = (range.end - range.begin) * unit_bytes;
        std::memcpy(b.destination.data() + range.begin * unit_bytes, b.staging.data() + slot, size);
        slot += size;
    }
}

struct CalibrationPoint {
    std::uint32_t regions;
    std::uint32_t units;
    double measured_ns;
};

CalibrationPoint calibrate(std::uint32_t regions, std::uint32_t units, std::uint32_t unit_bytes) {
    std::vector<Range> ranges;
    const auto per_region = units / regions;
    for (std::uint32_t n = 0; n < regions; ++n) {
        const auto start = n * (per_region + 3);
        ranges.push_back({start, start + per_region});
    }
    Buffers buffers(std::size_t(ranges.back().end) * unit_bytes);
    for (std::size_t index = 0; index < buffers.source.size(); ++index) {
        buffers.source[index] = std::uint8_t(index ^ (index >> 8) ^ 0x9d);
    }
    replay(ranges, unit_bytes, buffers);
    constexpr unsigned repetitions = 32;
    std::vector<double> values;
    for (unsigned sample = 0; sample < 11; ++sample) {
        const auto start = Clock::now();
        for (unsigned repeat = 0; repeat < repetitions; ++repeat) {
            replay(ranges, unit_bytes, buffers);
            std::atomic_signal_fence(std::memory_order_seq_cst);
        }
        values.push_back(elapsed_ns(start, Clock::now()) / repetitions);
        for (const auto range : ranges) {
            const auto offset = std::size_t(range.begin) * unit_bytes;
            const auto bytes = std::size_t(range.end - range.begin) * unit_bytes;
            if (std::memcmp(buffers.source.data() + offset, buffers.destination.data() + offset, bytes) != 0) {
                throw std::runtime_error("calibration copy mismatch");
            }
        }
    }
    return {regions, units, percentile(values, 50)};
}

struct Model {
    double intercept_ns;
    double region_ns;
    double unit_ns;
    Cost cost;
};

Model fit(const std::vector<CalibrationPoint>& training) {
    double average_regions = 0;
    double average_units = 0;
    double average_ns = 0;
    for (const auto& point : training) {
        average_regions += point.regions;
        average_units += point.units;
        average_ns += point.measured_ns;
    }
    average_regions /= training.size();
    average_units /= training.size();
    average_ns /= training.size();

    // The full Cartesian grid makes the two centered predictors orthogonal.
    double region_covariance = 0;
    double unit_covariance = 0;
    double region_variance = 0;
    double unit_variance = 0;
    for (const auto& point : training) {
        const auto d_regions = point.regions - average_regions;
        const auto d_units = point.units - average_units;
        const auto d_ns = point.measured_ns - average_ns;
        region_covariance += d_regions * d_ns;
        unit_covariance += d_units * d_ns;
        region_variance += d_regions * d_regions;
        unit_variance += d_units * d_units;
    }
    const auto region_ns = region_covariance / region_variance;
    const auto unit_ns = unit_covariance / unit_variance;
    const auto picoseconds = [](double nanoseconds) {
        return std::uint64_t(std::max(1.0, std::round(1000.0 * nanoseconds)));
    };
    return {
        average_ns - average_regions * region_ns - average_units * unit_ns,
        region_ns,
        unit_ns,
        {picoseconds(region_ns), picoseconds(unit_ns)},
    };
}

struct Workload {
    std::string_view name;
    std::vector<std::uint32_t> dirty;
    std::vector<Range> islands;
};

std::array<Workload, 4> workloads(std::uint32_t extent, std::uint32_t seed) {
    std::mt19937 random(seed);
    const auto draw = [&](std::uint32_t upper) { return std::uint32_t(random() % upper); };

    Workload dense{"dense-runs", {}, {{0, extent}}};
    for (std::uint32_t begin = 0; begin < extent; begin += 236) {
        for (std::uint32_t unit = begin; unit < std::min(extent, begin + 192); ++unit) {
            dense.dirty.push_back(unit);
        }
    }

    Workload sparse{"sparse-uniform", {}, {{0, extent}}};
    for (std::uint32_t unit = 0; unit < extent; ++unit) {
        if (draw(47) == 0) {
            sparse.dirty.push_back(unit);
        }
    }

    Workload clustered{"clustered-updates", {}, {{0, extent}}};
    for (std::uint32_t begin = 0; begin < extent; begin += 256 + draw(320)) {
        auto unit = begin;
        const auto runs = 7 + draw(10);
        for (std::uint32_t run = 0; run < runs && unit < extent; ++run) {
            const auto end = std::min(extent, unit + 1 + draw(7));
            for (; unit < end; ++unit) {
                clustered.dirty.push_back(unit);
            }
            unit = end + 1 + draw(18);
        }
    }
    std::sort(clustered.dirty.begin(), clustered.dirty.end());
    clustered.dirty.erase(std::unique(clustered.dirty.begin(), clustered.dirty.end()), clustered.dirty.end());

    Workload guarded{"mixed-ownership", {}, {}};
    std::uint32_t start = 0;
    while (start < extent) {
        const auto end = std::min(extent, start + 30 + draw(100));
        guarded.islands.push_back({start, end});
        auto unit = start;
        while (unit < end) {
            const auto dirty_end = std::min(end, unit + 1 + draw(5));
            for (; unit < dirty_end; ++unit) {
                guarded.dirty.push_back(unit);
            }
            unit = dirty_end + 1 + draw(14);
        }
        start = end + 1 + draw(28);
    }
    return {std::move(dense), std::move(sparse), std::move(clustered), std::move(guarded)};
}

struct Images {
    Buffers buffers;
    std::vector<std::uint8_t> initial;
    std::vector<std::uint8_t> expected;

    Images(const Workload& w, std::size_t bytes, std::size_t unit_bytes)
        : buffers(bytes), initial(bytes), expected(bytes) {
        for (std::size_t index = 0; index < bytes; ++index) {
            initial[index] = std::uint8_t((index * 31) ^ (index >> 7));
        }
        buffers.source = initial;
        expected = initial;
        for (const auto unit : w.dirty) {
            const auto base = unit * unit_bytes;
            for (std::size_t index = base; index < base + unit_bytes; ++index) {
                buffers.source[index] = expected[index] ^ 0xa5;
                expected[index] = buffers.source[index];
            }
        }
        std::size_t previous = 0;
        for (const auto island : w.islands) {
            for (std::size_t index = previous; index < island.begin * unit_bytes; ++index) {
                buffers.source[index] ^= 0x5a;
            }
            previous = island.end * unit_bytes;
        }
        for (std::size_t index = previous; index < bytes; ++index) {
            buffers.source[index] ^= 0x5a;
        }
    }
};

std::uint64_t validate(std::span<const Range> ranges, const Problem& problem) {
    std::uint32_t previous = 0;
    std::size_t island = 0;
    std::uint64_t total = 0;
    for (const auto op : ranges) {
        while (island < problem.islands.size() && problem.islands[island].end <= op.begin) {
            ++island;
        }
        if (op.begin < previous || op.begin >= op.end || op.end > problem.extent
            || op.end - op.begin > problem.max_units || island == problem.islands.size()
            || op.begin < problem.islands[island].begin || op.end > problem.islands[island].end) {
            throw std::runtime_error("invalid schedule, transfer replay aborted");
        }
        total += op.end - op.begin;
        previous = op.end;
    }
    return total;
}

struct Samples {
    std::vector<double> plan_ns;
    std::vector<double> replay_ns;
    std::vector<double> total_ns;
    std::uint64_t transferred_units = 0;
    std::size_t regions = 0;
};

std::array<Samples, 3> exercise(const Workload& w, std::uint32_t cap_bytes, const Options& opts, Cost cost) {
    const Problem problem{
        extent_bytes / opts.unit_bytes, cap_bytes / opts.unit_bytes, cost, w.dirty, w.islands,
    };
    Images images(w, extent_bytes, opts.unit_bytes);
    std::array<Samples, 3> data;
    std::mt19937 random(opts.seed ^ cap_bytes);
    constexpr unsigned warmup = 3;
    for (unsigned sample = 0; sample < warmup + opts.samples; ++sample) {
        std::array order{0u, 1u, 2u};
        for (std::size_t size = order.size(); size > 1; --size) {
            std::swap(order[size - 1], order[random() % size]);
        }
        for (const auto arm : order) {
            std::copy(images.initial.begin(), images.initial.end(), images.buffers.destination.begin());
            const auto plan_start = Clock::now();
            const auto plan = transfer::plan(problem, strategies[arm]);
            const auto plan_end = Clock::now();
            const auto units = validate(plan, problem);
            const auto replay_start = Clock::now();
            replay(plan, opts.unit_bytes, images.buffers);
            const auto replay_end = Clock::now();
            if (images.buffers.destination != images.expected) {
                throw std::runtime_error("complete destination mismatch");
            }
            auto& stats = data[arm];
            if (sample != 0 && (stats.transferred_units != units || stats.regions != plan.size())) {
                throw std::runtime_error("same input produced different transfer counts");
            }
            stats.transferred_units = units;
            stats.regions = plan.size();
            if (sample >= warmup) {
                stats.plan_ns.push_back(elapsed_ns(plan_start, plan_end));
                stats.replay_ns.push_back(elapsed_ns(replay_start, replay_end));
                stats.total_ns.push_back(stats.plan_ns.back() + stats.replay_ns.back());
            }
        }
    }
    return data;
}

void print_point(const CalibrationPoint& p, const Model& fit_model) {
    const auto predicted = fit_model.intercept_ns + fit_model.region_ns * p.regions + fit_model.unit_ns * p.units;
    std::cout << "{\"regions\":" << p.regions << ",\"units\":" << p.units
        << ",\"measured_ns\":" << p.measured_ns << ",\"predicted_ns\":" << predicted << '}';
}

void print_stats(const std::array<Samples, 3>& rows, std::size_t unit_bytes, Cost model) {
    for (std::size_t arm = 0; arm < rows.size(); ++arm) {
        const auto& row = rows[arm];
        std::vector<double> paired;
        for (std::size_t index = 0; index < row.total_ns.size(); ++index) {
            paired.push_back(row.total_ns[index] - rows[1].total_ns[index]);
        }
        std::cout << (arm == 0 ? "" : ",") << "\"" << names[arm] << "\":{"
            << "\"regions\":" << row.regions << ",\"transfer_bytes\":" << row.transferred_units * unit_bytes
            << ",\"modeled_cost_ps\":" << model.setup * row.regions + model.unit * row.transferred_units
            << ",\"median_plan_ns\":" << percentile(row.plan_ns, 50)
            << ",\"median_replay_ns\":" << percentile(row.replay_ns, 50)
            << ",\"median_total_ns\":" << percentile(row.total_ns, 50)
            << ",\"p95_total_ns\":" << percentile(row.total_ns, 95)
            << ",\"median_paired_total_delta_vs_greedy_ns\":" << percentile(paired, 50)
            << '}';
    }
}

int run(const Options& opts) {
    // Fit copy-only timings independently of the held-out workload families.
    // Keep the training points in one small-burst regime. Large memcpy pairs
    // need not share its bandwidth or marginal region cost.
    std::vector<CalibrationPoint> training;
    const auto max_training_regions = std::min(64u, (4 * kib) / opts.unit_bytes);
    for (const auto regions : {1u, max_training_regions / 2, max_training_regions}) {
        for (const auto bytes : {4 * kib, 16 * kib, 64 * kib}) {
            training.push_back(calibrate(regions, bytes / opts.unit_bytes, opts.unit_bytes));
        }
    }
    const Model model = fit(training);
    constexpr std::uint32_t validation_regions_a = 11;
    const auto validation_regions_b = std::min(47u, (53 * kib) / opts.unit_bytes);
    const auto validation_a = calibrate(
        validation_regions_a, (13 * kib / opts.unit_bytes / validation_regions_a) * validation_regions_a,
        opts.unit_bytes
    );
    const auto validation_b = calibrate(
        validation_regions_b, (53 * kib / opts.unit_bytes / validation_regions_b) * validation_regions_b,
        opts.unit_bytes
    );
    const auto larger_copy = calibrate(1, 256 * kib / opts.unit_bytes, opts.unit_bytes);
    const auto larger_batch = calibrate(64, 256 * kib / opts.unit_bytes, opts.unit_bytes);

    std::cout << std::fixed << std::setprecision(2)
        << "{\n\"backend\":\"cpu-two-memcpy-legs-one-batch\","
        << "\"timed_total\":\"plan_ns + replay_ns; resets and validators excluded\","
        << "\"samples\":" << opts.samples << ",\"seed\":" << opts.seed
        << ",\"extent_bytes\":" << extent_bytes << ",\"unit_bytes\":" << opts.unit_bytes
        << ",\"hardware_threads_hint\":" << std::thread::hardware_concurrency()
        << ",\"geometry\":\"synthetic, workload families and caps are not measured upstream frequencies\","
        << "\n\"copy_fit\":{\"raw_fixed_intercept_ns\":" << model.intercept_ns
        << ",\"raw_marginal_region_ns\":" << model.region_ns << ",\"raw_marginal_unit_ns\":" << model.unit_ns
        << ",\"quantized_region_ps\":" << model.cost.setup << ",\"quantized_unit_ps\":" << model.cost.unit
        << ",\"positive_fit\":" << (model.region_ns > 0 && model.unit_ns > 0 ? "true" : "false")
        << ",\"training_bytes_range\":[4096,65536]"
        << ",\"calibration_median_of\":11,\"replays_per_calibration_sample\":32,\"training\":[";
    for (std::size_t n = 0; n < training.size(); ++n) {
        std::cout << (n == 0 ? "" : ",");
        print_point(training[n], model);
    }
    std::cout << "],\"held_out\":[";
    print_point(validation_a, model);
    std::cout << ',';
    print_point(validation_b, model);
    std::cout << "],\"larger_copy_controls\":[";
    print_point(larger_copy, model);
    std::cout << ',';
    print_point(larger_batch, model);
    std::cout << "]},\n\"cases\":[";
    bool first = true;
    for (const auto& w : workloads(extent_bytes / opts.unit_bytes, opts.seed)) {
        for (const auto cap : caps_bytes) {
            const auto rows = exercise(w, cap, opts, model.cost);
            std::cout << (first ? "\n" : ",\n") << "{\"name\":\"" << w.name
                << "\",\"max_per_copy_staging_slot_bytes\":" << cap
                << ",\"dirty_units\":" << w.dirty.size() << ",\"ownership_islands\":" << w.islands.size() << ',';
            print_stats(rows, opts.unit_bytes, model.cost);
            std::cout << '}';
            first = false;
        }
    }
    std::cout << "\n]}\n";
    return 0;
}
} // namespace

int main(int argc, char** argv) {
    try {
        return run(parse(argc, argv));
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
