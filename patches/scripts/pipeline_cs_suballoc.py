from mesa_edit import replace

SUBALLOC_H = 'src/freedreno/vulkan/tu_suballoc.h'
SUBALLOC_CC = 'src/freedreno/vulkan/tu_suballoc.cc'
PIPELINE_CC = 'src/freedreno/vulkan/tu_pipeline.cc'
SHADER_CC = 'src/freedreno/vulkan/tu_shader.cc'

replace(
    SUBALLOC_H,
    'void\ntu_suballoc_bo_free(struct tu_suballocator *suballoc, struct tu_suballoc_bo *bo);',
    """void
tu_suballoc_bo_trim(struct tu_suballocator *suballoc,
                    struct tu_suballoc_bo *suballoc_bo,
                    uint32_t used_size);

void
tu_suballoc_bo_free(struct tu_suballocator *suballoc, struct tu_suballoc_bo *bo);""",
    'declare tu_suballoc_bo_trim',
)

replace(
    SUBALLOC_CC,
    'void\ntu_suballoc_bo_free(struct tu_suballocator *suballoc, struct tu_suballoc_bo *bo)',
    """void
tu_suballoc_bo_trim(struct tu_suballocator *suballoc,
                    struct tu_suballoc_bo *suballoc_bo,
                    uint32_t used_size)
{
   assert(used_size <= suballoc_bo->size);
   if (!suballoc->bo || suballoc->bo != suballoc_bo->bo)
      return;

   uint64_t offset = suballoc_bo->iova - suballoc->bo->iova;
   if (offset + suballoc_bo->size == suballoc->next_offset) {
      suballoc_bo->size = used_size;
      suballoc->next_offset = offset + used_size;
   }
}

void
tu_suballoc_bo_free(struct tu_suballocator *suballoc, struct tu_suballoc_bo *bo)""",
    'define tu_suballoc_bo_trim',
)

replace(
    PIPELINE_CC,
    """         if (!binding->array_size)
            continue;""",
    """         if (!binding->array_size ||
             (j == set_layout->binding_count - 1 &&
              set_layout->has_variable_descriptors))
            continue;""",
    'skip variable-count descriptor bindings in tu6_load_state_size',
)

replace(
    PIPELINE_CC,
    """      if (set_combined_state(builder, pipeline,
                             VK_GRAPHICS_PIPELINE_LIBRARY_PRE_RASTERIZATION_SHADERS_BIT_EXT |
                             VK_GRAPHICS_PIPELINE_LIBRARY_FRAGMENT_SHADER_BIT_EXT)) {
         size += tu6_load_state_size(pipeline, layout);
      }
   } else {
      size += tu6_load_state_size(pipeline, layout);
   }""",
    """      if (dev->physical_device->info->chip == A6XX &&
          set_combined_state(builder, pipeline,
                             VK_GRAPHICS_PIPELINE_LIBRARY_PRE_RASTERIZATION_SHADERS_BIT_EXT |
                             VK_GRAPHICS_PIPELINE_LIBRARY_FRAGMENT_SHADER_BIT_EXT)) {
         size += tu6_load_state_size(pipeline, layout);
      }
   } else if (dev->physical_device->info->chip == A6XX) {
      size += tu6_load_state_size(pipeline, layout);
   }""",
    'only reserve A6XX load_state CS space on A6XX',
)

replace(
    PIPELINE_CC,
    """   TU_RMV(cmd_buffer_suballoc_bo_create, dev, &pipeline->bo);
   tu_cs_init_suballoc(&pipeline->cs, dev, &pipeline->bo);

   return VK_SUCCESS;
}""",
    """   TU_RMV(cmd_buffer_suballoc_bo_create, dev, &pipeline->bo);
   tu_cs_init_suballoc(&pipeline->cs, dev, &pipeline->bo);

   return VK_SUCCESS;
}

static void
tu_pipeline_trim_cs(struct tu_device *dev, struct tu_pipeline *pipeline)
{
   if (unlikely(dev->vk.memory_trace_data.is_enabled) ||
       pipeline->cs.status != VK_SUCCESS || !pipeline->bo.bo)
      return;

   uint32_t *start = static_cast<uint32_t *>(tu_suballoc_bo_map(&pipeline->bo));
   uint32_t used = (pipeline->cs.cur - start) * sizeof(uint32_t);
   pipeline->cs.end = pipeline->cs.cur;

   mtx_lock(&dev->pipeline_mutex);
   tu_suballoc_bo_trim(&dev->pipeline_suballoc, &pipeline->bo, used);
   mtx_unlock(&dev->pipeline_mutex);
}""",
    'add tu_pipeline_trim_cs helper',
)

replace(
    PIPELINE_CC,
    '   tu_pipeline_builder_emit_state<CHIP>(builder, *pipeline);\n',
    '   tu_pipeline_builder_emit_state<CHIP>(builder, *pipeline);\n'
    '   tu_pipeline_trim_cs(builder->device, *pipeline);\n',
    'trim graphics pipeline suballoc CS tail',
)

replace(
    PIPELINE_CC,
    """   if (CHIP == A6XX) {
      tu6_emit_load_state(dev, &pipeline->base, layout);
   }

   tu_append_executable(&pipeline->base, v, nir_initial_disasm);""",
    """   if (CHIP == A6XX) {
      tu6_emit_load_state(dev, &pipeline->base, layout);
   }
   tu_pipeline_trim_cs(dev, &pipeline->base);

   tu_append_executable(&pipeline->base, v, nir_initial_disasm);""",
    'trim compute pipeline suballoc CS tail',
)

replace(
    SHADER_CC,
    """      if (safe_const) {
         tu_cs_begin_sub_stream(&shader->cs, vpc_size, &sub_cs);
         TU_CALLX(dev, tu6_emit_vpc)(&sub_cs, NULL, NULL, NULL, safe_const, NULL);
         shader->safe_const_binning_state =
            tu_cs_end_draw_state(&shader->cs, &sub_cs);
      }
   }

   return VK_SUCCESS;
}""",
    """      if (safe_const) {
         tu_cs_begin_sub_stream(&shader->cs, vpc_size, &sub_cs);
         TU_CALLX(dev, tu6_emit_vpc)(&sub_cs, NULL, NULL, NULL, safe_const, NULL);
         shader->safe_const_binning_state =
            tu_cs_end_draw_state(&shader->cs, &sub_cs);
      }
   }

   if (likely(!dev->vk.memory_trace_data.is_enabled) &&
       shader->cs.status == VK_SUCCESS && shader->bo.bo) {
      uint32_t *start = static_cast<uint32_t *>(tu_suballoc_bo_map(&shader->bo));
      uint32_t used = (shader->cs.cur - start) * sizeof(uint32_t);
      shader->cs.end = shader->cs.cur;
      mtx_lock(&dev->pipeline_mutex);
      tu_suballoc_bo_trim(&dev->pipeline_suballoc, &shader->bo, used);
      mtx_unlock(&dev->pipeline_mutex);
   }

   return VK_SUCCESS;
}""",
    'trim uploaded shader suballoc CS tail',
)
