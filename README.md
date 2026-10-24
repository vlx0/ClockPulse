# ClockPulse

**Живой такт процессора.** P- и E-ядра отдельно, теплокарта по времени, схема питания с кнопки.

**Автор:** darkshade ([@vlx0](https://github.com/vlx0))

**365 дней open source** · **неделя 9 — «Мониторинг»** · день 62.

Не CpuPulse: там нагрузка в % и кто жрёт. Здесь частота, гибрид и питание.

---

## Возможности

- P-ядра и E-ядра по `EfficiencyClass` Windows (на обычном CPU — одна цифра)
- мин/макс за сессию
- теплокарта: логические ядра × время
- смена схемы питания (экономия / баланс / производительность)
- живые МГц как в Диспетчере: база × `% Processor Performance` (P-state из powrprof на новых Intel почти не двигается)
- интервал 0,5…5 с
- только Win32, без pip

## Установка

```powershell
git clone https://github.com/vlx0/ClockPulse.git
cd ClockPulse
pythonw run_clockpulse.pyw
```

Или `start.bat`.

Нужен Windows 10+ и Python 3.10+. Внешних зависимостей нет.

## Лицензия

MIT. См. [LICENSE](LICENSE).
