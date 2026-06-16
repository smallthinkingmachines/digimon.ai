# digimon.ai — available commands

# list all commands
default:
    @just --list

# decompile an APK with jadx (usage: just decompile path/to/app.apk)
decompile apk:
    jadx -d apks/decompiled/{{file_stem(apk)}} {{apk}}
    @echo "Output: apks/decompiled/{{file_stem(apk)}}"

# extract resources from an APK with apktool (usage: just extract path/to/app.apk)
extract apk:
    apktool d {{apk}} -o apks/extracted/{{file_stem(apk)}}
    @echo "Output: apks/extracted/{{file_stem(apk)}}"

# search decompiled source for server URLs
find-endpoints name:
    @grep -r "https://" apks/decompiled/{{name}} --include="*.java" --include="*.kt" -l

# search decompiled source for a pattern (usage: just grep arena "api")
search name pattern:
    @grep -r "{{pattern}}" apks/decompiled/{{name}} --include="*.java" --include="*.kt" -n | head -50
