"""server/server_core/gpu_monitor.py — GPU/VRAM/system monitoring."""
import subprocess, platform, psutil

def get_gpu_info() -> dict:
    for smi in ["nvidia-smi",r"C:\Windows\System32\nvidia-smi.exe",r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"]:
        try:
            si = None
            if platform.system()=="Windows":
                si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW; si.wShowWindow=subprocess.SW_HIDE
            r=subprocess.run([smi,"--query-gpu=memory.used,memory.total,memory.free,utilization.gpu","--format=csv,noheader,nounits"],
                capture_output=True,text=True,timeout=5,startupinfo=si)
            if r.returncode==0:
                p=r.stdout.strip().split(",")
                return {"used_mb":float(p[0]),"total_mb":float(p[1]),"free_mb":float(p[2]),"gpu_util":float(p[3]),"available":True}
        except Exception: continue
    mem=psutil.virtual_memory()
    return {"used_mb":mem.used/(1024**2),"total_mb":mem.total/(1024**2),"free_mb":mem.available/(1024**2),
            "gpu_util":psutil.cpu_percent(),"available":False,"note":"GPU non detecte - RAM systeme"}

def get_system_info() -> dict:
    mem=psutil.virtual_memory()
    return {"cpu_percent":psutil.cpu_percent(interval=0.1),"ram_used_gb":round(mem.used/(1024**3),2),
            "ram_total_gb":round(mem.total/(1024**3),2),"ram_percent":mem.percent}
