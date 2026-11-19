"""
nucleo — librería común de cutly (sin CLI). La usan las tres líneas del proyecto:

    crear-shorts/   generar la demo en la VM            (escribe la toma en editor/crudo/)
    editor/shorts/  Short vertical: montar, fusionar con la cara, subtitular, verificar
    editor/directos/ clips 16:9 de un directo

Un módulo por responsabilidad; ninguno sabe nada de una línea concreta:

    rutas       dónde vive cada cosa del repo (carpetas de trabajo, glosario, fuentes)
    ffmpeg      localizar ffmpeg/ffprobe en Windows, macOS y Linux
    medios      leer vídeo/audio: probe, duración, audio mono, fotogramas en gris
    audio       energía cada 10 ms (rms + alta frecuencia), máscara de voz, sonoridad (LUFS)
    series      tramos consecutivos de una máscara muestreada (voz, cambios de imagen...)
    formato     el lienzo del Short: 1080x1920 @ 60, banda de la cara de 648 px, recorte 816x961
    toma        el contrato entre la Fase 1 y la Fase 2: <toma>.steps.jsonl y <toma>.mapa.md
    material    el material aportado (editor/crudo/) y el papel de cada archivo: material.json
    cortes      el registro de cortes videos-editados/_cortes.log (solo APPEND)
    transcripcion  faster-whisper con la configuración medida (large-v3-turbo + VAD) y sus formatos
    subtitulos  texto de los subtítulos: glosario, bloques y línea de tiempo (sin dibujar nada)

Los scripts importan así (desde cualquier carpeta del repo):

    sys.path.insert(0, <raíz del repo>)
    from nucleo import medios, audio
"""
