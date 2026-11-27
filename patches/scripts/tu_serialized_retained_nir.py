import re
import sys
from pathlib import Path

HEADER = Path('src/freedreno/vulkan/tu_pipeline.h')

text = HEADER.read_text()
if 'struct tu_serialized_nir' in text:
    print(f'{HEADER}: serialized retained NIR already present upstream')
    sys.exit()

nir_shaders = re.compile(
    r'struct tu_nir_shaders\n\{\n'
    r'   struct vk_pipeline_cache_object base;\n\n'
    r'   /\* This is optional, and is only filled out when a library pipeline is\n'
    r'    \* compiled with RETAIN_LINK_TIME_OPTIMIZATION_INFO\.\n'
    r'    \*/\n'
    r'   nir_shader \*nir\[(\w+)\];\n\};')
library_nir = re.compile(r'(   struct \{\n)      nir_shader \*nir;(\n      struct tu_shader_key key;\n)')

if not nir_shaders.search(text) or not library_nir.search(text):
    sys.exit(f'{HEADER}: anchor missing for serialized retained NIR')

text = nir_shaders.sub(lambda m: f'''struct tu_serialized_nir
{{
   void *data;
   size_t size;
}};

struct tu_nir_shaders
{{
   struct vk_pipeline_cache_object base;

   /* This is optional, and is only filled out when a library pipeline is
    * compiled with RETAIN_LINK_TIME_OPTIMIZATION_INFO.
    *
    * The NIR is kept serialized. Live NIR takes a 32 KiB ralloc slab for
    * every instruction size it uses, and an app that retains thousands of
    * libraries (CS2 pre-warming its pipeline cache) runs out of memory
    * mappings on Android.
    */
   struct tu_serialized_nir nir[{m.group(1)}];
}};''', text, count=1)
text = library_nir.sub(r'\1      struct tu_serialized_nir nir;\2', text, count=1)
HEADER.write_text(text)
print(f'{HEADER}: serialized retained NIR')
