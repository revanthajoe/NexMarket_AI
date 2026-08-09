import asyncio
import sys
import os

# Add the current directory to sys.path so we can import 'ai'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai.model_manager import model_manager

async def download_all():
    print("Starting sequential model download and cache process...")
    print("This will download the models one by one to prevent network overload.\n")
    
    # List of all models used in the system
    models_to_download = [
        "distilbert", 
        "xgboost", 
        "lstm", 
        "qwen_llm", 
        "qwen_vl", 
        "sdxl"
    ]
    
    for model_key in models_to_download:
        print(f"[{model_key}] Starting download/load...")
        try:
            # model_manager.session(model_key) automatically triggers the .load() method,
            # which in turn triggers transformers/diffusers to download the weights.
            # When the block exits, it unloads it from memory.
            async with model_manager.session(model_key) as svc:
                print(f"[{model_key}] Successfully downloaded and cached!\n")
        except Exception as e:
            print(f"[{model_key}] Failed to load: {e}\n")
            
    print("All sequential downloads complete! You can now start uvicorn safely.")

if __name__ == "__main__":
    asyncio.run(download_all())
