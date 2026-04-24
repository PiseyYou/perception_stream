#ifndef HARDWARE_MODE_HPP
#define HARDWARE_MODE_HPP

/**
 * @brief 硬件模式管理类（离线版本 - 手动配置）
 *
 * 替代 ROS2 版本的 HardwareDetector，不读取配置文件，
 * 而是通过构造函数或 setMode() 手动设置硬件模式
 */
class HardwareMode {
public:
    /**
     * @brief 构造函数
     * @param is_k100 true: K100 模式, false: bestmow 模式
     */
    explicit HardwareMode(bool is_k100 = true)
        : is_k100_(is_k100),
          hardware_model_(is_k100 ? "K100" : "bestmow") {}

    /**
     * @brief 判断是否为 K100 硬件
     * @return true: K100 模式, false: bestmow 模式
     */
    bool isK100Hardware() const {
        return is_k100_;
    }

    /**
     * @brief 获取硬件型号字符串
     * @return 硬件型号（"K100" 或 "bestmow"）
     */
    std::string getHardwareModel() const {
        return hardware_model_;
    }

    /**
     * @brief 设置硬件模式
     * @param is_k100 true: K100 模式, false: bestmow 模式
     */
    void setMode(bool is_k100) {
        is_k100_ = is_k100;
        hardware_model_ = is_k100 ? "K100" : "bestmow";
    }

    /**
     * @brief 获取模式描述
     * @return 模式描述字符串
     */
    std::string getModeDescription() const {
        if (is_k100_) {
            return "K100 mode: Full YOLO decoding, adaptive stereo params, label-aware filtering, morphology post-processing";
        } else {
            return "bestmow mode: Simplified label mapping, fixed stereo params, generic filtering, no morphology";
        }
    }

private:
    bool is_k100_;
    std::string hardware_model_;
};

#endif // HARDWARE_MODE_HPP
