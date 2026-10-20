#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

typedef const wchar_t *(__cdecl *get_name_fn)(unsigned int);
typedef unsigned int (__cdecl *get_version_fn)(void);

static void write_utf8(FILE *output, unsigned int id, const wchar_t *name)
{
    int size;
    char *buffer;

    if (name == NULL || *name == L'\0')
        return;

    size = WideCharToMultiByte(CP_UTF8, 0, name, -1, NULL, 0, NULL, NULL);
    if (size <= 1)
        return;

    buffer = (char *)malloc((size_t)size);
    if (buffer == NULL)
        return;

    WideCharToMultiByte(CP_UTF8, 0, name, -1, buffer, size, NULL, NULL);
    fprintf(output, "%u\t%s\n", id, buffer);
    free(buffer);
}

int main(int argc, char **argv)
{
    HMODULE module;
    get_name_fn get_name;
    get_version_fn get_version;
    FILE *output;
    unsigned int id;
    unsigned int maximum = 20000;

    if (argc < 3) {
        fprintf(stderr, "usage: dump_skill_names.exe elementskill.dll output.tsv [max-id]\n");
        return 2;
    }

    if (argc >= 4)
        maximum = (unsigned int)strtoul(argv[3], NULL, 10);

    module = LoadLibraryExA(argv[1], NULL,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (module == NULL)
        module = LoadLibraryA(argv[1]);
    if (module == NULL) {
        fprintf(stderr, "LoadLibrary failed: %lu\n", GetLastError());
        return 3;
    }

    get_name = (get_name_fn)GetProcAddress(module,
        "?GetName@ElementSkill@GNET@@SAPBGI@Z");
    get_version = (get_version_fn)GetProcAddress(module,
        "?GetVersion@ElementSkill@GNET@@SAIXZ");
    if (get_name == NULL) {
        fprintf(stderr, "GetName export not found\n");
        FreeLibrary(module);
        return 4;
    }

    output = fopen(argv[2], "wb");
    if (output == NULL) {
        fprintf(stderr, "cannot open output file\n");
        FreeLibrary(module);
        return 5;
    }

    fprintf(output, "# version\t%u\n", get_version != NULL ? get_version() : 0);
    for (id = 1; id <= maximum; ++id)
        write_utf8(output, id, get_name(id));

    fclose(output);
    FreeLibrary(module);
    return 0;
}
