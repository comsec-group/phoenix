#pragma once

#include "observer.hpp"
#include <algorithm>
#include <vector>

/// Simple composite that forwards every callback to each registered sink.
/// Lifetimes of the underlying observers are managed by the caller; the
/// FanOutObserver stores raw pointers and never deletes them.
class FanOutObserver final : public IHammerObserver {
    public:
    /// Construct from an initializer‑list or any container of IHammerObserver*.
    explicit FanOutObserver(std::vector<IHammerObserver*> sinks)
    : sinks_{ std::move(sinks) } {
        // remove nullptr entries defensively
        std::erase(sinks_, nullptr);
    }

    void on_pre_iteration(const FuzzPoint& fp) override {
        for(IHammerObserver* s : sinks_) {
            if(s != nullptr) {
                s->on_pre_iteration(fp);
            }
        }
    }

    void on_post_iteration(const FuzzPoint& fp, const std::vector<bit_flip_t>& flips) override {
        for(IHammerObserver* s : sinks_) {
            if(s != nullptr) {
                s->on_post_iteration(fp, flips);
            }
        }
    }

    private:
    std::vector<IHammerObserver*> sinks_;
};
