#include <torch/script.h>
#include <iostream>
#include <vector>
#include <memory>

extern "C" {
    __declspec(dllexport) void* load_model(const char* path) {
        try {
            auto module = std::make_unique<torch::jit::script::Module>(torch::jit::load(path));
            return module.release();
        } catch (const std::exception& e) {
            std::cerr << "Error loading model from " << path << ": " << e.what() << std::endl;
            return nullptr;
        }
    }

    __declspec(dllexport) void free_model(void* model) {
        if (model) {
            delete static_cast<torch::jit::script::Module*>(model);
        }
    }

    __declspec(dllexport) float run_inference(void* model, float spot, float strike_dist, float dte, float iv, float prev_delta, bool is_lstm) {
        if (!model) return 0.0f;
        auto* module = static_cast<torch::jit::script::Module*>(model);
        try {
            torch::Tensor input_tensor;
            if (is_lstm) {
                input_tensor = torch::tensor({spot, strike_dist, dte, iv, prev_delta}, torch::dtype(torch::kFloat32)).view({1, 1, 5});
            } else {
                input_tensor = torch::tensor({spot, strike_dist, dte, iv, prev_delta}, torch::dtype(torch::kFloat32)).view({1, 5});
            }
            std::vector<torch::jit::IValue> inputs;
            inputs.push_back(input_tensor);
            at::Tensor output = module->forward(inputs).toTensor();
            return output[0][0].item<float>();
        } catch (...) {
            return 0.0f;
        }
    }
}
