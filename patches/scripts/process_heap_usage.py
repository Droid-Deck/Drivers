from mesa_edit import replace

DEVICE = 'src/freedreno/vulkan/tu_device.cc'

# VK_EXT_memory_budget reports what the process has allocated, but each Vulkan instance
# enumerates its own physical device and heap.used counts that instance's memory alone. A D3D12
# game under Proton allocates through vkd3d-proton's instance and reads its usage through DXGI,
# whose DXVK instance has allocated nothing: it saw none of its own memory in use against a budget
# that shrinks with the system's free memory, and never trimmed until Android killed it. One
# driver library is loaded per process, so one counter beside heap.used covers every instance.
# heap.used still guards each instance's heap size.
replace(
    DEVICE,
    'static inline VkDeviceSize\ntu_get_budget_memory(',
    """/* DD-Turnip: device memory allocated by every Vulkan instance in this process. */
static uint64_t tu_process_heap_used;

static inline VkDeviceSize
tu_get_budget_memory(""",
    'process-wide heap usage counter',
)

replace(
    DEVICE,
    'memory_budget_props->heapUsage[0] = p_atomic_read(&physical_device->heap.used);',
    'memory_budget_props->heapUsage[0] = p_atomic_read(&tu_process_heap_used);',
    'memory budget reports the process-wide usage',
)

replace(
    DEVICE,
    """                       "Out of heap memory");
   }
   return VK_SUCCESS;
}""",
    """                       "Out of heap memory");
   }
   p_atomic_add(&tu_process_heap_used, bo->size);
   return VK_SUCCESS;
}""",
    'allocations counted process-wide',
)

replace(
    DEVICE,
    '      p_atomic_add(&device->physical_device->heap.used, -mem->bo->size);\n',
    '      p_atomic_add(&device->physical_device->heap.used, -mem->bo->size);\n'
    '      p_atomic_add(&tu_process_heap_used, -mem->bo->size);\n',
    'frees counted process-wide',
)
