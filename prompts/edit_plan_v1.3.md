Построй безопасный keep-plan для Reels. Храни диапазоны, которые нужно оставить.
Не удаляй фразы, если это искажает смысл, причинно-следственную связь, факты или CTA.
При низкой уверенности используй review. Время — секунды по исходной timeline.
Keep/removed ranges не должны перекрываться, обязаны находиться внутри source duration.
`estimated_duration` должна точно равняться сумме длительностей всех `keep_ranges`.
## FINAL JSON CHECK BEFORE RESPONSE

Before returning the JSON object, perform a self-check:

- Calculate every keep_ranges interval duration:
  end - start

- Sum all keep_ranges durations.

- Set estimated_duration equal to this exact sum.

- Do not estimate this value.
- Do not use source duration.
- Do not use rounded values.

Example:

keep_ranges:
[
  {"start":0,"end":5},
  {"start":10,"end":15}
]

estimated_duration must be:
10

If estimated_duration does not match the sum of keep_ranges, regenerate the JSON before answering.