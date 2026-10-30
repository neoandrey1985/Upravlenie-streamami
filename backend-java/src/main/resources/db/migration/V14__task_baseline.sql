-- v2.12: базовый план «Ганта по иерархии» — зафиксированные плановые сроки элемента (JSON: a — начало, b — конец, at — дата фиксации).

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS baseline TEXT;
