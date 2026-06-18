import ctypes
import os
import sys

def main():
    print("Attempting to load torch libraries via ctypes...")
    torch_lib_dir = r"C:\Users\User\Desktop\Affinity-Core\backend_orchestrator\.venv\Lib\site-packages\torch\lib"
    os.add_dll_directory(torch_lib_dir)
    
    # Load torch dependencies first
    try:
        ctypes.CDLL(os.path.join(torch_lib_dir, "libiomp5md.dll"))
        print("Loaded libiomp5md.dll")
        ctypes.CDLL(os.path.join(torch_lib_dir, "c10.dll"))
        print("Loaded c10.dll")
        ctypes.CDLL(os.path.join(torch_lib_dir, "torch_cpu.dll"))
        print("Loaded torch_cpu.dll")
    except Exception as e:
        print(f"Failed to load dependencies: {e}")
        return

    # Now load torch_inference.dll
    dll_path = r"C:\Users\User\Desktop\Affinity-Core\cpp_engine\build\torch_inference.dll"
    print(f"Loading {dll_path}...")
    try:
        dll = ctypes.CDLL(dll_path)
        print("SUCCESSFULLY LOADED torch_inference.dll!")
        
        # Test function pointers
        dll.load_model.restype = ctypes.c_void_p
        dll.load_model.argtypes = [ctypes.c_char_p]
        
        dll.free_model.argtypes = [ctypes.c_void_p]
        dll.free_model.restype = None
        
        dll.run_inference.restype = ctypes.c_float
        dll.run_inference.argtypes = [
            ctypes.c_void_p, # model
            ctypes.c_float,  # spot
            ctypes.c_float,  # strike_dist
            ctypes.c_float,  # dte
            ctypes.c_float,  # iv
            ctypes.c_float,  # prev_delta
            ctypes.c_bool    # is_lstm
        ]
        
        models = {
            "ffnn": r"C:\Users\User\Desktop\Affinity-Core\models\deep_hedge_ffnn.pt",
            "lstm": r"C:\Users\User\Desktop\Affinity-Core\models\deep_hedge_lstm.pt",
            "adversarial": r"C:\Users\User\Desktop\Affinity-Core\models\deep_hedge_adversarial.pt"
        }
        
        loaded_models = {}
        for name, path in models.items():
            print(f"Loading model {name} from {path}...")
            ptr = dll.load_model(path.encode('utf-8'))
            print(f"Model pointer for {name}: {ptr}")
            if ptr:
                loaded_models[name] = ptr
                
        # Run inference test
        spot = 150.0
        strike_dist = 0.02
        dte = 0.08
        iv = 0.25
        prev_delta = 0.5
        
        for name, ptr in loaded_models.items():
            is_lstm = (name == "lstm")
            res = dll.run_inference(ptr, spot, strike_dist, dte, iv, prev_delta, is_lstm)
            print(f"Model {name} inference result: {res}")
            
        # Free models
        for name, ptr in loaded_models.items():
            dll.free_model(ptr)
            print(f"Freed model {name}")
            
    except Exception as e:
        print(f"Failed to load torch_inference.dll: {e}")

if __name__ == "__main__":
    main()

