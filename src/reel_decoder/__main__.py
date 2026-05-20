"""CLI entrypoint — `python -m reel_decoder decode <path>` or `decode-all`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.pipeline import decode_reel

console = Console()
app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def decode(
    video_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    force: list[str] = typer.Option(
        None,
        "--force",
        "-f",
        help="Force re-run of one or more steps. Pass multiple times: -f classify -f vision",
    ),
):
    """Decode a single reel video file."""
    decoded = decode_reel(video_path, force_steps=force or [])
    console.print(f"\n[bold]Hook pattern:[/bold] {decoded.hook.pattern.value}")
    console.print(f"[bold]Hook text:[/bold] {decoded.hook.text}")
    console.print(f"[bold]Beats:[/bold] {len(decoded.beats)}")
    console.print(f"[bold]Why it works:[/bold] {decoded.why_it_works}")
    console.print(f"\nDecoded JSON: {settings.reel_dir(video_path.stem) / 'decoded.json'}")
    console.print(f"Swipe library: {settings.swipe_library_path}")


@app.command(name="decode-all")
def decode_all(
    force: list[str] = typer.Option(None, "--force", "-f"),
):
    """Decode every video in inputs/reels/."""
    inputs = settings.inputs_dir
    if not inputs.exists():
        console.print(f"[red]Inputs dir not found: {inputs}[/red]")
        raise typer.Exit(1)

    videos = sorted(
        p
        for p in inputs.iterdir()
        if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
    )
    if not videos:
        console.print(f"[yellow]No video files found in {inputs}[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found {len(videos)} video(s)")
    failures: list[tuple[Path, Exception]] = []
    for v in videos:
        try:
            decode_reel(v, force_steps=force or [])
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]FAILED {v.name}: {e}[/red]")
            failures.append((v, e))

    console.rule()
    console.print(f"[green]Completed: {len(videos) - len(failures)}/{len(videos)}[/green]")
    if failures:
        for v, e in failures:
            console.print(f"  [red]✗[/red] {v.name}: {e}")
        raise typer.Exit(1)


@app.command()
def reset_reel(
    video_path: Path = typer.Argument(..., exists=True, dir_okay=False),
):
    """Wipe all intermediate artifacts for a reel (forces full re-run)."""
    import shutil

    reel_dir = settings.reel_dir(video_path.stem)
    if reel_dir.exists():
        shutil.rmtree(reel_dir)
        console.print(f"[yellow]Removed {reel_dir}[/yellow]")
    else:
        console.print(f"Nothing to remove for {video_path.stem}")


@app.command()
def doctor():
    """Diagnose the environment — check ffmpeg, Ollama, and model availability."""
    import shutil
    import subprocess

    import ollama

    ok = True

    # ffmpeg
    if shutil.which("ffmpeg"):
        console.print("[green]✓[/green] ffmpeg found")
    else:
        console.print("[red]✗[/red] ffmpeg NOT found — install it")
        ok = False

    # Ollama
    try:
        client = ollama.Client(host=settings.ollama_host)
        response = client.list()
        names = [m.model for m in response.models]
        console.print(f"[green]✓[/green] Ollama running at {settings.ollama_host}")
        for required in (settings.vision_model, settings.classifier_model):
            present = any(required in n for n in names)
            mark = "[green]✓[/green]" if present else "[red]✗[/red]"
            console.print(f"  {mark} {required}")
            if not present:
                console.print(f"     run: ollama pull {required}")
                ok = False
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗[/red] Ollama unreachable: {e}")
        ok = False

    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
