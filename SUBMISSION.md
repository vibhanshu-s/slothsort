---
title: "SlothSort: let your downloads folder tidy itself"
published: true
tags: devchallenge, hf26challenge, gemma, opensource
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

SlothSort is a small local assistant for the Downloads folder that keeps becoming a second desktop. It looks at loose filenames and file details, asks a local open-weight model for a tidy plan, then gives the person who owns the files the last word.

The aim is deliberately modest: avoid the little decisions that make sorting a folder feel like work. A readable name, a reasonable folder, and the option to leave something alone.

## Demo

Try the [sample demo](https://vibhanshu-s.github.io/slothsort/). The hosted page shows a fixed example pile; it does not connect to a visitor's files or run AI. For local scanning and AI suggestions, follow the setup in the [README](https://github.com/vibhanshu-s/slothsort#run-it-locally).

## Code

The source is on [GitHub](https://github.com/vibhanshu-s/slothsort).

## How I Built It

The local app is a small Python server with a plain HTML, CSS, and JavaScript interface. It binds to `127.0.0.1`. The default model is Gemma 3 1B through Ollama, so the model runs on the same computer as the files.

SlothSort only scans the selected folder's top level. It gives the model filenames and extensions; it never reads file contents. File sizes and modification times stay local, where the server uses them to display useful details and catch stale plans. A small extension map picks predictable destination folders, while Gemma suggests a calmer filename and explains obvious cleanup such as a trailing “copy” or “final v3”. The server checks the suggestions, then the interface lets me review each row and untick anything I don't want moved. If a destination already exists, the batch stops before changing anything. The latest move can be undone while the app is open.

## Why Does Open Innovation Matter?

This job touches personal files, and the model does not need their contents to make a useful first pass. Local inference keeps even the filenames and metadata on the same computer. There is no hosted API key, recurring inference bill, or folder upload to trust with a list of someone's downloads.

Open weights also make the small model choice visible and replaceable. SlothSort can use another model installed in Ollama; the same local workflow remains available when the laptop is offline after the model is downloaded.

## Prize Categories

- Best Use of Gemma
