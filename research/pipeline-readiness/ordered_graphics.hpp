// SPDX-License-Identifier: MIT
#pragma once

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <functional>
#include <future>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace portbridge {

// The caller owns one immutable recipe per key and keeps the backend alive
// until the queue is destroyed. Only the first request for a key builds it.
class PipelineQueue {
public:
    PipelineQueue(std::size_t recipe_count, std::size_t workers, std::function<void(std::size_t)> compile)
        : jobs_(recipe_count), ready_(recipe_count), compile_(std::move(compile)) {
        if (!workers || !recipe_count) throw std::invalid_argument("empty pipeline queue");
        workers_.reserve(workers);
        try {
            for (std::size_t i = 0; i < workers; ++i) {
                workers_.emplace_back([this](std::stop_token stop) { run(stop); });
            }
        } catch (...) {
            stop_workers();
            throw;
        }
    }

    ~PipelineQueue() { stop_workers(); }

    void request(std::size_t recipe) {
        {
            std::lock_guard lock(mutex_);
            auto& ready = ready_.at(recipe);
            if (ready.valid()) return;
            // Prepare every potentially throwing operation before publishing
            // the job. Workers cannot see the new queue entry under this lock.
            std::packaged_task<void()> task([this, recipe] { compile_(recipe); });
            auto future = task.get_future().share();
            pending_.push_back(recipe);
            jobs_[recipe] = std::move(task);
            ready = std::move(future);
        }
        work_.notify_one();
    }

    void wait(std::size_t recipe) {
        request(recipe);
        std::shared_future<void> result;
        {
            std::lock_guard lock(mutex_);
            result = ready_.at(recipe);
        }
        result.get();
    }

private:
    void stop_workers() {
        {
            std::lock_guard lock(mutex_);
            stopping_ = true;
        }
        for (auto& worker : workers_) worker.request_stop();
    }

    void run(std::stop_token stop) {
        while (!stop.stop_requested()) {
            std::packaged_task<void()> task;
            {
                std::unique_lock lock(mutex_);
                if (!work_.wait(lock, stop, [this] { return !pending_.empty(); })) return;
                if (stop.stop_requested() || stopping_) return;
                const auto recipe = pending_.front();
                pending_.pop_front();
                task = std::move(jobs_[recipe]);
            }
            task();
        }
    }

    std::mutex mutex_;
    std::condition_variable_any work_;
    std::deque<std::size_t> pending_;
    std::vector<std::packaged_task<void()>> jobs_;
    std::vector<std::shared_future<void>> ready_;
    std::function<void(std::size_t)> compile_;
    bool stopping_ = false;
    // Destroy first: request stop and join while shared state is still alive.
    std::vector<std::jthread> workers_;
};

// One compatibility block with stable draw state and owned arguments. Flush
// before a command whose state cannot be represented in Draw, at the configured
// packet limit, or before ending the block. A failed compile aborts playback.
template<class Draw>
class OrderedDraws {
public:
    OrderedDraws(PipelineQueue& pipelines, std::size_t capacity)
        : pipelines_(pipelines), capacity_(capacity) {
        if (!capacity_) throw std::invalid_argument("empty draw window");
        draws_.reserve(capacity_);
    }

    template<class Emit>
    void append(std::size_t recipe, Draw draw, const Emit& emit) {
        if (failed_) throw std::logic_error("failed draw window");
        pipelines_.request(recipe);
        if (draws_.size() == capacity_) flush(emit);
        draws_.emplace_back(recipe, std::move(draw));
    }

    template<class Emit>
    void flush(const Emit& emit) {
        if (failed_) throw std::logic_error("failed draw window");
        try {
            for (const auto& [recipe, draw] : draws_) {
                pipelines_.wait(recipe);
                emit(recipe, draw);
            }
        } catch (...) {
            failed_ = true;
            draws_.clear();
            throw;
        }
        draws_.clear();
    }

private:
    PipelineQueue& pipelines_;
    std::size_t capacity_;
    std::vector<std::pair<std::size_t, Draw>> draws_;
    bool failed_ = false;
};

} // namespace portbridge
