# XFormers Installation Guide

## Problem

XFormers cannot be installed via pip on Windows 10/11 due to Windows' default 260-character MAX_PATH limitation. XFormers has deeply nested source directories that exceed this limit during compilation.

```
ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: 
'C:\\Users\\HP\\AppData\\Local\\Temp\\pip-install-nkzhz4pe\\xformers_e9019e93826f450e830df41f0dc23761\\third_party\\flash-attention\\csrc\\composable_kernel\\...'
```

## Impact

- **XFormers not required**: The backend functions without xformers. It's an optimization for SDXL (Stable Diffusion XL) image generation.
- **Performance**: Without xformers, SDXL uses PyTorch's native attention mechanism, which is slightly less memory-efficient but fully functional.
- **Functionality**: All AI features (LLM, vision, forecasting, lead prediction, etc.) work normally.

## Solutions (in order of preference)

### Option 1: Enable Windows Long Paths (RECOMMENDED - Permanent Solution)

Run this PowerShell command as **Administrator**:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Then restart PowerShell and retry:
```bash
pip install xformers>=0.0.27
```

**Note**: Restart your terminal after enabling this setting.

### Option 2: Install via Conda (Workaround)

If you have Conda installed:

```bash
conda install xformers
```

Conda handles long paths natively on Windows.

### Option 3: Use a Pre-compiled Wheel

Some older xformers versions have pre-compiled wheels:

```bash
# For Python 3.11, CUDA 11.8+
pip install xformers==0.0.24
```

**Caveat**: This may downgrade torch to 2.2.0 (requires adjustment).

### Option 4: Accept the Limitation (Current Default)

The backend is fully functional without xformers. SDXL will use standard PyTorch attention, which trades memory efficiency for availability. For most use cases, this is acceptable.

## Verification

To verify xformers is installed:

```bash
python -c "import xformers; print(xformers.__version__)"
```

If not installed, you'll see:
```
ModuleNotFoundError: No module named 'xformers'
```

This is non-blocking and the application will function normally.

## References

- [XFormers GitHub](https://github.com/facebookresearch/xformers)
- [Windows Long Paths Support](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)
- [PyTorch SDXL Documentation](https://pytorch.org/vision/main/models.html)
