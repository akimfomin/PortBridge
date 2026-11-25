#pragma once

#include <condition_variable>
#include <cstddef>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

namespace point_workers {

struct Block {
    std::size_t begin = 0;
    std::size_t end = 0;
    std::size_t edited_count = 0;
    std::size_t begin_retained = 0;
    std::size_t begin_edited = 0;
};

inline std::vector<Block> make_blocks(std::size_t count, std::size_t workers)
{
    std::vector<Block> blocks(workers);
    for (std::size_t worker = 0; worker < workers; ++worker) {
        blocks[worker].begin = count * worker / workers;
        blocks[worker].end = count * (worker + 1) / workers;
    }
    return blocks;
}

class WorkerTeam {
public:
    explicit WorkerTeam(std::vector<Block>& blocks) : blocks_(blocks)
    {
        threads_.reserve(blocks.size() - 1);
        for (std::size_t worker = 1; worker < blocks.size(); ++worker) {
            threads_.emplace_back([this, worker](std::stop_token stop) {
                operate(blocks_[worker], stop);
            });
        }
    }

    template<class Work>
    void run(Work work)
    {
        if (threads_.empty()) {
            work(blocks_.front());
            return;
        }
        {
            std::lock_guard lock(mutex_);
            job_ = work;
            remaining_ = threads_.size();
            ++generation_;
        }
        available_.notify_all();
        work(blocks_.front());
        std::unique_lock lock(mutex_);
        completed_.wait(lock, [this] { return remaining_ == 0; });
        job_ = {};
    }

private:
    void operate(Block& block, std::stop_token stop)
    {
        std::size_t seen = 0;
        while (true) {
            std::unique_lock lock(mutex_);
            if (!available_.wait(lock, stop, [&] { return generation_ != seen; })) {
                return;
            }
            seen = generation_;
            auto work = job_;
            lock.unlock();
            work(block);
            lock.lock();
            if (--remaining_ == 0) {
                completed_.notify_one();
            }
        }
    }

    std::vector<Block>& blocks_;
    std::mutex mutex_;
    std::condition_variable_any available_;
    std::condition_variable completed_;
    std::function<void(Block&)> job_;
    std::size_t remaining_ = 0;
    std::size_t generation_ = 0;
    std::vector<std::jthread> threads_;
};

}  // namespace point_workers
