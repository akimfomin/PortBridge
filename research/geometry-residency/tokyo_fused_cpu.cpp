#include "point_workers.hpp"

#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using point_workers::Block;
using point_workers::make_blocks;
using point_workers::WorkerTeam;

struct Point {
    float x;
    float y;
    float z;
};

static_assert(sizeof(Point) == 3 * sizeof(float));
static_assert(std::endian::native == std::endian::little);

struct Source {
    std::vector<Point> position;
    std::vector<std::int32_t> point_class;
    std::vector<std::int32_t> intensity;

    explicit Source(std::size_t count)
        : position(count), point_class(count), intensity(count) {}
};

struct Snapshot {
    std::vector<Point> position;
    std::vector<std::int32_t> id;
    std::vector<std::int32_t> point_class;
    std::vector<std::int32_t> intensity;

    explicit Snapshot(std::size_t count)
        : position(count), id(count), point_class(count), intensity(count) {}
};

template<class Value>
void read_vector(std::ifstream& stream, std::vector<Value>& values)
{
    stream.read(reinterpret_cast<char*>(values.data()),
                static_cast<std::streamsize>(sizeof(Value) * values.size()));
    if (!stream) {
        throw std::runtime_error("Truncated source array");
    }
}

template<class Value>
void write_vector(std::ofstream& stream, const std::vector<Value>& values)
{
    stream.write(reinterpret_cast<const char*>(values.data()),
                 static_cast<std::streamsize>(sizeof(Value) * values.size()));
    if (!stream) {
        throw std::runtime_error("Could not write snapshot");
    }
}

Source read_source(const fs::path& path)
{
    std::ifstream stream(path, std::ios::binary);
    std::array<char, 4> magic{};
    std::uint32_t count = 0;
    stream.read(magic.data(), magic.size());
    stream.read(reinterpret_cast<char*>(&count), sizeof(count));
    if (!stream || magic != std::array<char, 4>{'P', 'B', 'P', 'C'} || count != 6'385'097) {
        throw std::runtime_error("Source is not the pinned Tokyo fixture");
    }
    Source source(count);
    read_vector(stream, source.position);
    read_vector(stream, source.point_class);
    read_vector(stream, source.intensity);
    if (stream.peek() != std::ifstream::traits_type::eof()) {
        throw std::runtime_error("Unrecognised payload after source arrays");
    }
    return source;
}

bool selected(const Source& source, std::size_t i, float threshold)
{
    return source.position[i].x < threshold && source.point_class[i] == 1;
}

std::size_t edit(const Source& source, Snapshot& output, float threshold,
                 std::vector<Block>& blocks, WorkerTeam& team)
{
    team.run([&](Block& block) {
        block.edited_count = 0;
        for (std::size_t i = block.begin; i < block.end; ++i) {
            block.edited_count += selected(source, i, threshold);
        }
    });
    std::size_t edited_count = 0;
    for (const Block& block : blocks) {
        edited_count += block.edited_count;
    }
    std::size_t retained = 0;
    std::size_t edited = source.position.size() - edited_count;
    for (Block& block : blocks) {
        block.begin_retained = retained;
        block.begin_edited = edited;
        retained += (block.end - block.begin) - block.edited_count;
        edited += block.edited_count;
    }
    team.run([&](Block& block) {
        std::size_t retain_output = block.begin_retained;
        std::size_t edit_output = block.begin_edited;
        for (std::size_t i = block.begin; i < block.end; ++i) {
            const bool change = selected(source, i, threshold);
            const std::size_t j = change ? edit_output++ : retain_output++;
            const Point point = source.position[i];
            output.position[j] = Point{point.x, point.y, change ? 0.0f : point.z};
            output.id[j] = static_cast<std::int32_t>(i);
            output.point_class[j] = change ? 2 : source.point_class[i];
            output.intensity[j] = source.intensity[i];
        }
    });
    return edited_count;
}

int main(int argc, char** argv)
{
    try {
        if (argc != 5) {
            std::cerr << "usage: tokyo_fused_cpu input.bin snapshots-dir threads rounds\n";
            return 2;
        }
        const auto workers = std::stoul(argv[3]);
        const auto rounds = std::stoul(argv[4]);
        if (workers < 1 || workers > 64 || rounds < 1) {
            throw std::runtime_error("Invalid thread or round count");
        }
        const fs::path folder(argv[2]);
        if (!fs::create_directories(folder)) {
            throw std::runtime_error("Use a new snapshot directory");
        }
        const Source input = read_source(argv[1]);
        Snapshot output(input.position.size());
        auto blocks = make_blocks(input.position.size(), workers);
        WorkerTeam team(blocks);
        const std::array<float, 4> thresholds{-125.0f, -25.0f, 35.0f, 125.0f};
        for (const float threshold : thresholds) {
            edit(input, output, threshold, blocks, team);
        }
        std::cout << "threads,round,threshold_x_m,selected_points,elapsed_ms\n";
        for (std::size_t round = 1; round <= rounds; ++round) {
            for (const float threshold : thresholds) {
                const auto start = std::chrono::steady_clock::now();
                const auto changed = edit(input, output, threshold, blocks, team);
                const auto stop = std::chrono::steady_clock::now();
                const auto ms = std::chrono::duration<double, std::milli>(stop - start).count();
                std::cout << workers << ',' << round << ',' << threshold << ',' << changed
                          << ',' << std::fixed << std::setprecision(6) << ms << '\n';
            }
        }
        for (const float threshold : thresholds) {
            edit(input, output, threshold, blocks, team);
            const auto label = std::to_string(static_cast<int>(threshold));
            std::ofstream stream(folder / ("snapshot-" + label + ".bin"), std::ios::binary);
            if (!stream) {
                throw std::runtime_error("Could not open output snapshot");
            }
            write_vector(stream, output.id);
            write_vector(stream, output.point_class);
            write_vector(stream, output.intensity);
            write_vector(stream, output.position);
        }
    }
    catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
