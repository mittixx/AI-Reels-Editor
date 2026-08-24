# Motion Canvas asset generator

Это отдельный TypeScript-проект Motion Canvas 3.17.2. Он создаёт только motion assets;
его MP4-файлы добавляются в `media_manifest.json` и затем попадают в HyperFrames master timeline.

`npm run render:asset -- --input JOB.json --output motion.mp4 --job-id UNIQUE_ID` запускается
Python-адаптером. Каждый job работает в отдельной runtime/output-папке; принимается только точно
ожидаемый свежий и валидный MP4 текущего job.
Wrapper использует headless Chromium, потому что официальный Motion Canvas 3.17.2 не предоставляет
стабильную документированную headless CLI-команду. После `npm ci` выполните локальную команду
`.\node_modules\.bin\playwright.cmd install chromium` один раз.
