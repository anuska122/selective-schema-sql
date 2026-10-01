---
title: Selective Schema Text To SQL
emoji: 🗄️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Selective-schema text-to-SQL API

Answers natural-language questions over 11 databases (75 tables, 798 columns)
by retrieving only the relevant tables instead of prompting with the whole
schema. Source and measured results: https://github.com/anuska122/selective-schema-sql

`POST /ask` requires the `x-api-token` header and is rate limited. All SQL runs
through a read-only Postgres role with a statement timeout and a row cap.
