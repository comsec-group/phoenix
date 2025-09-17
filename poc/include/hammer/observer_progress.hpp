#pragma once

#include "observer.hpp"

#include <indicators/progress_bar.hpp>
#include <sstream>
#include <vector>

class ProgressBarObserver final : public IHammerObserver {
    public:
    explicit ProgressBarObserver(std::size_t total_iterations)
    : total_iterations_{ total_iterations }, iterations_done_{ 0 },
      bar_(indicators::option::BarWidth{ 20 },
           indicators::option::Start{ "[" },
           indicators::option::Fill{ "=" },
           indicators::option::Lead{ ">" },
           indicators::option::End{ "]" },
           indicators::option::ForegroundColor{ indicators::Color::cyan },
           indicators::option::ShowElapsedTime{ true },
           indicators::option::ShowRemainingTime{ true },
           indicators::option::MaxProgress{ total_iterations_ },
           indicators::option::PostfixText{ "" }) {
    }

    void on_pre_iteration(const FuzzPoint& fp) override {
        update_postfix(fp);
    }

    void on_post_iteration(const FuzzPoint& fp, const std::vector<bit_flip_t>& flips) override {
        ++iterations_done_;
        last_flips_ = static_cast<int>(flips.size());
        total_flips_ += last_flips_;
        update_postfix(fp);
        bar_.tick();
    }

    ~ProgressBarObserver() override {
        bar_.mark_as_completed();
    }

    private:
    void update_postfix(const FuzzPoint& fp) {
        std::ostringstream s;
        s << "it=" << iterations_done_ << "/" << total_iterations_
          << " | len=" << fp.pattern.size() << " | agg_base_row=" << fp.agg_base_row
          << " | sync=" << fp.self_sync_threshold << " | r/tREFI=" << fp.pattern_reads_per_trefi
          << " | BF+ " << last_flips_ << " | BFΣ " << total_flips_ << " ";
        bar_.set_option(indicators::option::PostfixText{ s.str() });
    }

    std::size_t total_iterations_{};
    std::size_t iterations_done_;
    indicators::ProgressBar bar_;
    int last_flips_  = 0;
    int total_flips_ = 0;
};
