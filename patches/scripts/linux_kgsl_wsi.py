from mesa_edit import replace

KGSL = 'src/freedreno/vulkan/tu_knl_kgsl.cc'
DEVICE = 'src/freedreno/vulkan/tu_device.cc'

replace(KGSL, '#include <sys/mman.h>', '#include <sys/mman.h>\n#include <sys/stat.h>\n#include <sys/sysmacros.h>', 'sys/stat includes')
replace(KGSL, '   result = tu_physical_device_init(device, instance);', '''   struct stat kgsl_st;
   if (fstat(fd, &kgsl_st) == 0 && S_ISCHR(kgsl_st.st_mode)) {
      device->has_local = device->has_master = true;
      device->local_major = device->master_major = major(kgsl_st.st_rdev);
      device->local_minor = device->master_minor = minor(kgsl_st.st_rdev);
   }

   result = tu_physical_device_init(device, instance);''', 'KGSL device numbers for dma-buf feedback')
replace(DEVICE, '.EXT_physical_device_drm = !is_kgsl(device->instance),', '.EXT_physical_device_drm = !is_kgsl(device->instance) || device->has_local,', 'EXT_physical_device_drm on KGSL')
