# SlothSort

**Let the pile wait less.** SlothSort is a local-first file tidy-up assistant for the downloads folder you keep meaning to sort. It asks an open-weight model running on your computer to suggest calmer filenames and sensible folders, then waits for you to review every move.

## Try the sample

Open [the hosted demo](https://vibhanshu-s.github.io/slothsort/). It uses a fixed sample pile so you can click around without connecting a folder or sending data anywhere. It does not run AI or move files in the hosted version.

## Run it locally

1. Install [Ollama](https://ollama.com/download) and Python 3.10 or newer.
2. Open a terminal and download the small Gemma model once:

   ```powershell
   ollama pull gemma3:1b
   ```

3. In a second terminal, open this folder and start SlothSort:

   ```powershell
   python server.py
   ```

4. Visit [http://127.0.0.1:8080](http://127.0.0.1:8080). SlothSort fills in your Downloads folder as a starting point. Choose a different folder if you prefer.

The server uses only Python's standard library. After the model is downloaded, inference and file operations run on your machine. Pick any model installed in Ollama from the model menu. You can set a different default with `SLOTHSORT_MODEL`.

## Privacy and safety

- The server binds to `127.0.0.1` and does not expose an internet-facing API.
- SlothSort reads filenames, file sizes, and modification times in the folder's top level. It never opens file contents or scans subfolders.
- Only filenames and extensions are sent to Ollama on your own computer for the local model to suggest cleaner names. File size and modified time stay in the local app.
- A plan is only a suggestion. You can untick individual files. Nothing moves until you press **Tidy selected**.
- Existing destination names stop the whole batch before anything moves. The latest pass can be undone while the local app is open.
- The hosted page only renders an example. It cannot access a visitor's files or call an AI service.

## Built with

- Python's `http.server` and standard library filesystem APIs
- [Ollama](https://ollama.com/) for local inference
- Gemma 3 1B, an open-weight model, as the default model
- Vanilla HTML, CSS, and JavaScript

## Challenge

This project was created for the [Hacktoberfest Open-Source AI Challenge: Week 3 — Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19), in the **Best Use of Gemma** category.

## License

MIT. See [LICENSE](LICENSE).
