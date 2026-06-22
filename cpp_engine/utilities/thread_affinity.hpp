#pragma once
#include <cstdlib>
#include <cstdio>
#include <string>

#if defined(_WIN32) || defined(_WIN64)
#include <windows.h>
#ifdef ERROR
#undef ERROR
#endif
#endif

namespace utilities {

inline void pin_thread_to_core(const std::string& env_var_name, const std::string& thread_name_for_log) {
    const char* env_val = std::getenv(env_var_name.c_str());
    if (env_val == nullptr) {
        return;
    }
    int core_id = std::atoi(env_val);
    if (core_id < 0 || core_id >= 64) {
        std::printf("[%s Affinity] Invalid core index: %d (must be 0-63)\n", thread_name_for_log.c_str(), core_id);
        return;
    }

#if defined(_WIN32) || defined(_WIN64)
    HANDLE thread_handle = GetCurrentThread();
    DWORD_PTR mask = static_cast<DWORD_PTR>(1) << core_id;
    DWORD_PTR prev_mask = SetThreadAffinityMask(thread_handle, mask);
    if (prev_mask == 0) {
        std::printf("[%s Affinity] FAILED to pin thread to core %d (error %lu)\n", thread_name_for_log.c_str(), core_id, GetLastError());
        std::fflush(stdout);
    } else {
        std::printf("[%s Affinity] Pinned thread to core %d\n", thread_name_for_log.c_str(), core_id);
        std::fflush(stdout);
    }
#else
    std::printf("[%s Affinity] Pinned thread to core %d (mocked on non-Windows)\n", thread_name_for_log.c_str(), core_id);
    std::fflush(stdout);
#endif
}

} // namespace utilities
