#ifndef HARDWARE_DETECTOR_HPP
#define HARDWARE_DETECTOR_HPP

#include <string>

class HardwareDetector {
public:
    static HardwareDetector& getInstance() {
        static HardwareDetector instance;
        return instance;
    }

    std::string getHardwareModel() const {
        return "x86_simulation";
    }

    std::string getDetectionStatus() const {
        return "offline_mode";
    }

    bool isK100Hardware() const {
        return false;  // 离线测试环境默认不是 K100
    }

private:
    HardwareDetector() = default;
    ~HardwareDetector() = default;
    HardwareDetector(const HardwareDetector&) = delete;
    HardwareDetector& operator=(const HardwareDetector&) = delete;
};

#endif // HARDWARE_DETECTOR_HPP
