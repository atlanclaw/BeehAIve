---
docid: "00000000-0000-0000-0000-000000000001"
title: "PKB Dashboard"
created_at: "2026-04-10T00:00:00Z"
status: "active"
topics: ["system", "dashboard"]
categories: ["admin"]
---

# PKB Dashboard

## Aktive Projekte
```dataview
TABLE title, status, topics, created_at
FROM "10-projects"
WHERE status = "active"
SORT created_at DESC
```

## Offene Inbox

```dataview
LIST
FROM "50-inbox"
SORT file.mtime DESC
LIMIT 20
```

## Neueste Referenzen

```dataview
TABLE title, topics, categories
FROM "30-references"
SORT created_at DESC
LIMIT 10
```
