"""Shared helpers: works both as a Claude Code plugin and as a manual install."""
import datetime, json, os, re
from pathlib import Path

MIN_LEVEL = 1000  # anything smaller is a typo or a stray number, not a threshold


def data_dir() -> Path:
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    p = Path(d) if d else Path.home() / ".claude" / "token-saver"
    p.mkdir(parents=True, exist_ok=True)
    return p


def opt(name: str, default: str) -> str:
    """Plugin option (set in /config) > TS_* env var > default."""
    for key in (f"CLAUDE_PLUGIN_OPTION_{name.upper()}", f"TS_{name.upper()}"):
        v = os.environ.get(key)
        if v not in (None, ""):
            return v
    return default


def log(msg: str) -> None:
    try:
        with open(data_dir() / "hook.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


# ---- thresholds -------------------------------------------------------------------------
# There is no built-in threshold: the user chooses one. It comes from, in order,
# the plugin option / TS_WARN_TOKENS, then the value saved by the first-run question.

_NUMBER = re.compile(r"(\d+(?:[.,]\d+)*)\s*(k|m|bin|milyon)?(?![a-z0-9])")
_MULT = {None: 1, "k": 1_000, "bin": 1_000, "m": 1_000_000, "milyon": 1_000_000}


def _numbers(text, suffix):
    """One matched number run -> list of floats. Handles 150.000 / 150,000 (thousands),
    1.5 / 1,5 (decimal, only with a suffix) and 150,300 (two values)."""
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text) or re.fullmatch(r"\d{1,3}(,000)+", text):
        return [float(re.sub(r"[.,]", "", text))]
    if suffix and re.fullmatch(r"\d+,\d{1,2}", text):
        return [float(text.replace(",", "."))]
    out = []
    for part in text.split(","):
        try:
            out.append(float(part))
        except ValueError:
            pass
    return out


def parse_levels(raw):
    """"150k, 300k" / "150000,300000" / "1.5m" / "150.000" -> sorted token counts.
    Entries that can't be read, or are under MIN_LEVEL, are skipped. May return []."""
    levels = set()
    for m in _NUMBER.finditer(str(raw).lower()):
        for n in _numbers(m.group(1), m.group(2)):
            try:
                v = int(n * _MULT[m.group(2)])
            except (ValueError, OverflowError):
                continue
            if MIN_LEVEL <= v <= 10**9:
                levels.add(v)
    return sorted(levels)


def config_file() -> Path:
    return data_dir() / "config.json"


def load_config() -> dict:
    try:
        d = json.loads(config_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_config(**changes) -> None:
    cfg = load_config()
    cfg.update(changes)
    config_file().write_text(json.dumps(cfg), encoding="utf-8")


def thresholds():
    """Returns (levels, source). source is "settings", "saved", "off" or None (not chosen yet)."""
    levels = parse_levels(opt("warn_tokens", ""))
    if levels:
        return levels, "settings"
    cfg = load_config()
    if cfg.get("off") is True:
        return [], "off"
    saved = cfg.get("levels")
    if isinstance(saved, list):
        levels = sorted({int(v) for v in saved
                         if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= MIN_LEVEL})
        if levels:
            return levels, "saved"
    return [], None


def fmt(n) -> str:
    """152000 -> "152k", 1500000 -> "1.5M"."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    return f"{n/1000:.0f}k"
