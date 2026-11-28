# PortBridge — текущая передача

## Результаты · 28 ноября 2026

- **Continued добавил проверку фрагментации, предложенную PortBridge.** Автор получил 32 и 1 МиБ крупнейшего свободного блока при одинаковом объёме живых данных. Готовый контроль передан KytyPS5. [Решение Continued](https://github.com/ProjectLeonida/mandy/pull/2547#issuecomment-7232162430) · [Передача KytyPS5](https://github.com/KytyPS5/KytyPS5/pull/1394#issuecomment-7232365939)
- **Два патча переданы внешним командам.** Исправление AnyXboxX проверено с реальной блокировкой файла Windows. Автор Xbox2Windows отклонил узкую поправку FP16: она покрывает одно значение, хотя ещё три находятся близко к порогу округления. PortBridge перепроверил расчёт и обновил задание на независимый GPU-прогон. [Патчи и тесты](evidence/decision-followthrough/result-pass-2026-11-28/acceptance.md#исправления-и-проверки) · [Lab #155](https://github.com/akimfomin/PortBridge/issues/155)
- **Девять исправлений и улучшений PortBridge вошли в main.** Проверенные результаты Lab снова видны в сводке Action. Поиск различает точный SHA сохранённой записи и текстовое упоминание. Прошли 335 тестов и проверка экспорта. [PR #154](https://github.com/akimfomin/PortBridge/pull/154) · [PR #156](https://github.com/akimfomin/PortBridge/pull/156) · [main](https://github.com/akimfomin/PortBridge/commit/1bf55cc3a937205f43d90b2edde1be27558f2c82)
- **Десять решений сверены, два получены в этой итерации.** Подтверждено одно новое применение проверки. Новых независимых GPU-результатов и согласованных подключений сторонних агентов пока нет. Полностью принятых новых требований нет. Реестр содержит 81 verified, 40 partial, 1 blocked. [Таблица решений, требования и команды воспроизведения](evidence/decision-followthrough/result-pass-2026-11-28/acceptance.md)

[Предыдущая передача](https://github.com/akimfomin/PortBridge/blob/00cbdf250c9d68799a52e870dce86f1398947a9d/audit/LATEST.md)
