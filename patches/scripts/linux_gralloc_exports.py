from mesa_edit import replace

DEVICE = 'src/freedreno/vulkan/tu_device.cc'
HEADER = 'src/freedreno/vulkan/tu_device.h'

replace(HEADER,
        '   /* for dedicated allocations */\n'
        '   struct tu_image *image;\n'
        '};\n',
        '   /* for dedicated allocations */\n'
        '   struct tu_image *image;\n'
        '\n'
        '   uint64_t display_buffer_id;\n'
        '};\n',
        'display buffer id on device memory')

replace(DEVICE,
        '#include "tu_wsi.h"\n',
        '#include "tu_wsi.h"\n'
        '#include "util/simple_mtx.h"\n'
        '#include <sys/socket.h>\n'
        '#include <sys/un.h>\n',
        'socket includes')

replace(DEVICE,
        'VKAPI_ATTR VkResult VKAPI_CALL\n'
        'tu_AllocateMemory(VkDevice _device,\n',
        '''#define TU_DISPLAY_BUFFER_MAGIC 0x42444444u
#define TU_DISPLAY_BUFFER_VERSION 1u
#define TU_DISPLAY_BUFFER_ALLOC 1u
#define TU_DISPLAY_BUFFER_FREE 2u

struct tu_display_buffer_request {
   uint32_t magic;
   uint32_t version;
   uint32_t op;
   uint32_t width;
   uint32_t height;
   uint32_t format;
   uint32_t stride;
   uint32_t offset;
   uint64_t size;
   uint64_t id;
   uint64_t modifier;
};

struct tu_display_buffer_reply {
   uint32_t magic;
   uint32_t status;
   uint64_t id;
   uint64_t size;
};

static simple_mtx_t tu_display_buffer_lock = SIMPLE_MTX_INITIALIZER;
static int tu_display_buffer_socket = -1;
static bool tu_display_buffer_absent;

static int
tu_display_buffer_connect(void)
{
   if (tu_display_buffer_socket >= 0)
      return tu_display_buffer_socket;
   if (tu_display_buffer_absent)
      return -1;

   const char *dir = getenv("XDG_RUNTIME_DIR");
   struct sockaddr_un addr = { .sun_family = AF_UNIX };
   if (!dir || snprintf(addr.sun_path, sizeof(addr.sun_path),
                        "%s/droiddeck-display-buffers", dir) >=
                  (int) sizeof(addr.sun_path)) {
      tu_display_buffer_absent = true;
      return -1;
   }

   int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
   if (fd < 0)
      return -1;

   struct timeval timeout = { .tv_sec = 2 };
   setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
   setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

   if (connect(fd, (struct sockaddr *) &addr, sizeof(addr)) != 0) {
      close(fd);
      tu_display_buffer_absent = true;
      return -1;
   }

   tu_display_buffer_socket = fd;
   return fd;
}

static void
tu_display_buffer_drop(void)
{
   close(tu_display_buffer_socket);
   tu_display_buffer_socket = -1;
}

static uint32_t
tu_display_buffer_format(VkFormat format)
{
   switch (format) {
   case VK_FORMAT_R8G8B8A8_UNORM:
   case VK_FORMAT_R8G8B8A8_SRGB:
      return DRM_FORMAT_ABGR8888;
   case VK_FORMAT_B8G8R8A8_UNORM:
   case VK_FORMAT_B8G8R8A8_SRGB:
      return DRM_FORMAT_ARGB8888;
   case VK_FORMAT_A2B10G10R10_UNORM_PACK32:
      return DRM_FORMAT_ABGR2101010;
   default:
      return 0;
   }
}

static int
tu_display_buffer_alloc(const struct tu_image *image, uint64_t size,
                        uint64_t *id)
{
   const struct fdl_layout *layout = &image->layout[0];
   const uint32_t format = tu_display_buffer_format(image->vk.format);
   const bool compressed = layout->ubwc &&
                           fdl_tile_mode(layout, 0) == TILE6_3 &&
                           layout->ubwc_slices[0].offset == 0 &&
                           layout->slices[0].offset == layout->ubwc_layer_size;
   const bool linear = !layout->ubwc && layout->tile_mode == TILE6_LINEAR &&
                       layout->slices[0].offset == 0;

   if (!format || image->vk.image_type != VK_IMAGE_TYPE_2D ||
       image->vk.mip_levels != 1 || image->vk.array_layers != 1 ||
       image->vk.samples != VK_SAMPLE_COUNT_1_BIT ||
       !(image->vk.usage & (VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT |
                            VK_IMAGE_USAGE_STORAGE_BIT)) ||
       (!compressed && !linear) || layout->cpp != 4 || size < layout->size)
      return -1;

   struct tu_display_buffer_request request = {
      .magic = TU_DISPLAY_BUFFER_MAGIC,
      .version = TU_DISPLAY_BUFFER_VERSION,
      .op = TU_DISPLAY_BUFFER_ALLOC,
      .width = image->vk.extent.width,
      .height = image->vk.extent.height,
      .format = format,
      .stride = fdl_pitch(layout, 0),
      .offset = layout->slices[0].offset,
      .size = size,
      .modifier = compressed ? DRM_FORMAT_MOD_QCOM_COMPRESSED
                             : DRM_FORMAT_MOD_LINEAR,
   };
   struct tu_display_buffer_reply reply = {};
   char control[CMSG_SPACE(sizeof(int))] = {};
   struct iovec iov = { .iov_base = &reply, .iov_len = sizeof(reply) };
   struct msghdr msg = {
      .msg_iov = &iov,
      .msg_iovlen = 1,
      .msg_control = control,
      .msg_controllen = sizeof(control),
   };
   int buffer = -1;

   simple_mtx_lock(&tu_display_buffer_lock);
   int fd = tu_display_buffer_connect();
   if (fd >= 0) {
      ssize_t n = send(fd, &request, sizeof(request), MSG_NOSIGNAL);
      if (n == (ssize_t) sizeof(request)) {
         do {
            n = recvmsg(fd, &msg, MSG_CMSG_CLOEXEC);
         } while (n < 0 && errno == EINTR);
      }
      for (struct cmsghdr *c = n >= 0 ? CMSG_FIRSTHDR(&msg) : NULL; c;
           c = CMSG_NXTHDR(&msg, c)) {
         if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS &&
             c->cmsg_len == CMSG_LEN(sizeof(int)))
            memcpy(&buffer, CMSG_DATA(c), sizeof(int));
      }
      if (n != (ssize_t) sizeof(reply) ||
          reply.magic != TU_DISPLAY_BUFFER_MAGIC) {
         tu_display_buffer_drop();
         if (buffer >= 0)
            close(buffer);
         buffer = -1;
      } else if (reply.status != 0 || reply.size < size) {
         if (buffer >= 0)
            close(buffer);
         buffer = -1;
      }
   }
   simple_mtx_unlock(&tu_display_buffer_lock);

   if (buffer >= 0)
      *id = reply.id;
   return buffer;
}

static void
tu_display_buffer_free(uint64_t id)
{
   struct tu_display_buffer_request request = {
      .magic = TU_DISPLAY_BUFFER_MAGIC,
      .version = TU_DISPLAY_BUFFER_VERSION,
      .op = TU_DISPLAY_BUFFER_FREE,
      .id = id,
   };

   simple_mtx_lock(&tu_display_buffer_lock);
   if (tu_display_buffer_socket >= 0 &&
       send(tu_display_buffer_socket, &request, sizeof(request),
            MSG_NOSIGNAL) != (ssize_t) sizeof(request))
      tu_display_buffer_drop();
   simple_mtx_unlock(&tu_display_buffer_lock);
}

VKAPI_ATTR VkResult VKAPI_CALL
tu_AllocateMemory(VkDevice _device,
''',
        'display buffer client')

replace(DEVICE,
        '      VkMemoryPropertyFlags mem_property =\n'
        '         device->physical_device->memory.types[pAllocateInfo->memoryTypeIndex];\n'
        '\n'
        '      result = _tu_init_memory(device, mem, mem_property, alloc_flags,\n'
        '                               pAllocateInfo->allocationSize, alignment,\n'
        '                               client_address,\n'
        '                               name);\n',
        '      VkMemoryPropertyFlags mem_property =\n'
        '         device->physical_device->memory.types[pAllocateInfo->memoryTypeIndex];\n'
        '\n'
        '      const VkMemoryDedicatedAllocateInfo *display_info =\n'
        '         vk_find_struct_const(pAllocateInfo->pNext, MEMORY_DEDICATED_ALLOCATE_INFO);\n'
        '      int display_buffer = -1;\n'
        '      if (is_kgsl(device->instance) && display_info &&\n'
        '          display_info->image != VK_NULL_HANDLE && export_info &&\n'
        '          (export_info->handleTypes &\n'
        '           VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT) &&\n'
        '          !client_address &&\n'
        '          !(mem_property & VK_MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT))\n'
        '         display_buffer = tu_display_buffer_alloc(\n'
        '            tu_image_from_handle(display_info->image),\n'
        '            pAllocateInfo->allocationSize, &mem->display_buffer_id);\n'
        '\n'
        '      if (display_buffer >= 0) {\n'
        '         result = tu_bo_init_dmabuf(device, &mem->bo,\n'
        '                                    pAllocateInfo->allocationSize, alignment,\n'
        '                                    TU_BO_ALLOC_NO_FLAGS, display_buffer);\n'
        '         close(display_buffer);\n'
        '         if (result != VK_SUCCESS) {\n'
        '            tu_display_buffer_free(mem->display_buffer_id);\n'
        '            mem->display_buffer_id = 0;\n'
        '            display_buffer = -1;\n'
        '         }\n'
        '      }\n'
        '\n'
        '      if (display_buffer < 0)\n'
        '         result = _tu_init_memory(device, mem, mem_property, alloc_flags,\n'
        '                                  pAllocateInfo->allocationSize, alignment,\n'
        '                                  client_address,\n'
        '                                  name);\n',
        'display buffers for exported image memory')

replace(DEVICE,
        '   tu_memory_emit_report(device, mem, /* alloc_info */ NULL, VK_SUCCESS);\n'
        '\n'
        '   _tu_destroy_memory(device, mem);\n',
        '   tu_memory_emit_report(device, mem, /* alloc_info */ NULL, VK_SUCCESS);\n'
        '\n'
        '   if (mem->display_buffer_id)\n'
        '      tu_display_buffer_free(mem->display_buffer_id);\n'
        '\n'
        '   _tu_destroy_memory(device, mem);\n',
        'display buffer release')
