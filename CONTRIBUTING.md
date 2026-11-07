# Contributing to Fortnite Cosmetics Browser

Thanks for helping out! This is a small project, so the process is simple.

## Reporting bugs and ideas

- Search [existing issues](https://github.com/248Tech/fortnite-cosmetics-browser/issues) first.
- Use the bug report or feature request template. For bugs, say whether it happens in the desktop app, the web demo or both, and include screenshots if you can.

## Making changes

1. Fork the repo and create a branch: `git checkout -b my-fix`
2. **Desktop app:** everything lives in `fortnite_cosmetics_browser.pyw` (Python 3.10+, Tkinter, Pillow).
   ```bash
   pip install -r requirements.txt
   python fortnite_cosmetics_browser.pyw
   ```
3. **Web demo:** plain HTML, CSS and JavaScript in `docs/`, no build step. Serve it locally:
   ```bash
   python -m http.server 8000 --directory docs
   ```
   then open http://localhost:8000.
4. Keep the two versions consistent when a change affects both (for example data parsing or fortnite.com links).
5. Open a pull request describing what changed and how you tested it.

## Guidelines

- Keep it dependency-light: the desktop app needs only Pillow, and the web demo uses no libraries.
- Don't commit cached data, build output or game assets.
- Be kind and constructive.

## Releases

Maintainers tag a version (`git tag v1.2.3 && git push --tags`). GitHub Actions then builds `FortniteCosmeticsBrowser.exe` and attaches it to the release.
