# Архитектурные решения — AI Reels Editor v1.3.4

## ADR-001: один ControlService

CLI и будущие API/GUI используют один `ControlService`. Команды `new`, `status`, `resume`
не имеют отдельной бизнес-логики. Это исключает расхождение поведения интерфейсов.

## ADR-002: HyperFrames — master timeline

HyperFrames 0.8.12 создаёт финальную композицию: A-roll, voice, hook, subtitles, B-roll и
motion assets. FFmpeg готовит технический base edit и выполняет QC. Motion Canvas не создаёт
вторую master timeline.

## ADR-003: Motion Canvas как asset generator

Motion Canvas 3.17.2 получает `motion_plan.json` и structured job JSON. Компоненты закреплены
в библиотеке. Из-за отсутствия стабильной документированной headless CLI в upstream 3.17.2
wrapper управляет официальным Vite UI через локальный Playwright Chromium. Ошибка останавливает
только зависимый stage и допускает resume.

## ADR-004: keep-plan и неизменяемый source

`edit_plan.json` хранит ranges, которые нужно оставить. Исходное видео читается и хэшируется,
но никогда не удаляется и не перезаписывается. Производные файлы находятся в project workspace.

## ADR-005: selective invalidation

Dependency graph — кодовая policy. Revision hook/B-roll/subtitles сбрасывает только зависимые
stages. Файлы прошлых результатов остаются на диске для аудита, но их manifest-record перестаёт
считаться валидным.

Input hash вычисляется до признания stage завершённым и включает все влияющие upstream artifacts,
config/preset, prompt и component versions. Motion render предшествует media manifest: только
проверенный output конкретного уникального job попадает в manifest и master timeline.

## ADR-006: Responses API + Pydantic

OpenAI adapter использует официальный Responses API `responses.parse` с Pydantic structured
outputs. Provider импортируется лениво, ключ читается только из `.env`, ошибки нормализуются.

## ADR-007: CapCut без выдуманного API

CapCut — только finishing package. Bridge формирует draft, SRT, plans, manifest и список только
оставшихся ручных задач. Публикация/GUI не выполняются автоматически.
