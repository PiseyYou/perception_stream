# 段错误修复说明

## 问题
程序运行时出现段错误（退出码139），导致闪退。

## 根本原因
在 `Config` 结构体中包含了 `HardwareMode` 对象：
```cpp
struct Config {
    // ...
    HardwareMode hardware_mode{true};  // ❌ 这会导致段错误
};
```

当 `OfflinePerceptionProcessor` 构造函数复制 Config 时：
```cpp
OfflinePerceptionProcessor(const Config &cfg) : config_(cfg) {}
```

复制 `HardwareMode` 对象可能触发内存访问错误。

## 解决方案
移除 Config 中的对象，只保留布尔标志：
```cpp
struct Config {
    // ...
    bool use_k100_mode = true;  // ✅ 只用布尔值
};
```

在需要显示模式描述时，直接使用条件判断：
```cpp
if (config.use_k100_mode) {
    cout << "  - K100 mode: Full YOLO decoding, ..." << endl;
} else {
    cout << "  - bestmow mode: Simplified label mapping, ..." << endl;
}
```

## 验证
所有测试用例通过：
- ✅ K100 + Mode 6
- ✅ K100 + Mode 7
- ✅ bestmow + Mode 6
- ✅ bestmow + Mode 7
- ✅ 默认模式

## 经验教训
1. **避免在POD结构体中包含复杂对象**：Config 这样的配置结构应该只包含基本类型
2. **优先使用基本类型**：bool、int、float 等不会有复制问题
3. **对象管理要谨慎**：如果必须使用对象，考虑使用指针或引用
