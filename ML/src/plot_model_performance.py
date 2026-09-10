"""
Draw the model's report card.

Six panels, each answering one question:
  1. How good is the ranking?            (precision-recall curve)
  2. Is it consistent across regions?    (per-fold spatial CV)
  3. Does it beat chance on REAL data?   (independent WRI validation)
  4. Do the probabilities mean anything? (calibration bands)
  5. Which clues does it use?            (feature importance)
  6. How does it compare to v1?          (honest vs inflated)
"""

from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import GroupKFold

SCORES = Path("data/processed/hotspot_scores_enriched.csv")
FEATURES_FILE = Path("data/processed/hotspot_features_2025.csv")
MODEL_FILE = Path("models/hotspot_static_source_model.joblib")
OUT = Path("outputs/model_performance.png")

BLOCK_SIZE, N_SPLITS = 20, 5
INK, MUTED = "#1a1a1a", "#8a8a8a"
BLUE, RED, GREEN, PURPLE = "#2563eb", "#dc2626", "#16a34a", "#7c3aed"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "#d4d4d4", "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.grid": True, "grid.color": "#ececec", "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
})

df = pd.read_csv(SCORES)
train = df[df["label"] >= 0].copy()
y = train["label"].values
p = train["static_probability"].values

fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.5))
fig.suptitle(
    "ThermoStats  -  place-level static thermal source model  -  report card",
    fontsize=14, fontweight="bold", y=0.98,
)

# ---- 1. Precision-recall curve -------------------------------------------
ax = axes[0][0]
prec, rec, _ = precision_recall_curve(y, p)
ap = average_precision_score(y, p)
ax.plot(rec, prec, color=BLUE, lw=2.2, label=f"ML model  (PR-AUC {ap:.3f})")

for col, colour, name in [
    ("active_days", "#f59e0b", "active_days alone"),
    ("night_fraction", MUTED, "night_fraction alone"),
]:
    s = train[col].rank(pct=True).values
    pr2, rc2, _ = precision_recall_curve(y, s)
    ax.plot(rc2, pr2, color=colour, lw=1.5, ls="--",
            label=f"{name}  ({average_precision_score(y, s):.3f})")

base = y.mean()
ax.axhline(base, color=RED, lw=1.2, ls=":", label=f"chance ({base:.3%})")
ax.set_xlabel("Recall  (share of real static sources found)")
ax.set_ylabel("Precision  (share of alerts that are correct)")
ax.set_title("1.  Ranking quality, tested on held-out regions")
ax.legend(fontsize=8, loc="upper right", framealpha=0.95)
ax.set_ylim(-0.03, 1.03)

# ---- 2. Per-fold consistency ---------------------------------------------
ax = axes[0][1]
groups = (
    (np.floor(train["latitude"] / BLOCK_SIZE).astype(int) + 100) * 1000
    + np.floor(train["longitude"] / BLOCK_SIZE).astype(int)
)
X_dummy = np.zeros((len(train), 1))
fold_ap = []
for _, test_idx in GroupKFold(n_splits=N_SPLITS).split(X_dummy, y, groups):
    fold_ap.append(average_precision_score(y[test_idx], p[test_idx]))

bars = ax.bar(range(1, N_SPLITS + 1), fold_ap, color=BLUE, width=0.6)
mean_ap = float(np.mean(fold_ap))
ax.axhline(mean_ap, color=RED, lw=1.5, ls="--",
           label=f"mean {mean_ap:.3f} +/- {np.std(fold_ap):.3f}")
for b, v in zip(bars, fold_ap):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.3f}",
            ha="center", fontsize=8.5)
ax.set_xlabel("Spatial fold  (each tests a different part of the world)")
ax.set_ylabel("PR-AUC")
ax.set_title("2.  Consistency across unseen regions")
ax.set_ylim(0, 1.12)
ax.legend(fontsize=8)

# ---- 3. Independent validation -------------------------------------------
ax = axes[0][2]
human = df[~df["is_volcanic"]]
base_rate = df["near_power_plant"].mean()
truth = human["near_power_plant"].values


def top_k_rate(values, k=500, repeats=200, seed=0):
    """Hit rate in the top k, with TIES BROKEN AT RANDOM.

    Needed because night_fraction has ~15,000 places tied at exactly 1.0.
    Taking them in file order silently re-ranks them by whatever the file
    happens to be sorted by, which invents a result that is not real.
    Returns mean and spread across repeated random tie-breaks.
    """
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    out = [
        truth[np.lexsort((rng.random(len(v)), -v))[:k]].mean()
        for _ in range(repeats)
    ]
    return float(np.mean(out)), float(np.std(out))


methods = [
    ("ML model", "static_probability", BLUE),
    ("NASA type2", "type2_fraction", "#0891b2"),
    ("active_days", "active_days", "#f59e0b"),
    ("night_fraction", "night_fraction", MUTED),
]
names, vals, errs, colours = [], [], [], []
for label, col, colour in methods:
    mean, sd = top_k_rate(human[col].values)
    names.append(label)
    vals.append(mean * 100)
    errs.append(sd * 100)
    colours.append(colour)
names.append("chance")
vals.append(base_rate * 100)
errs.append(0.0)
colours.append(RED)

bars = ax.barh(names[::-1], vals[::-1], xerr=errs[::-1], color=colours[::-1],
               height=0.6, error_kw={"ecolor": INK, "lw": 1.1, "capsize": 3})
for b, v in zip(bars, vals[::-1]):
    ax.text(v + max(vals) * 0.035, b.get_y() + b.get_height() / 2,
            f"{v:.1f}%  ({v / (base_rate * 100):.0f}x)",
            va="center", fontsize=8.5)
ax.set_xlabel("% of top 500 within 2 km of a real thermal power plant")
ax.set_title("3.  Independent check (WRI data - never seen by model)")
ax.set_xlim(0, max(vals) * 1.45)
ax.grid(axis="y", visible=False)
ax.text(0.99, 0.02, "ties broken at random, mean of 200 draws",
        transform=ax.transAxes, ha="right", fontsize=7.2,
        style="italic", color=MUTED)

# ---- 4. Calibration -------------------------------------------------------
ax = axes[1][0]
bands = [(0.99, 1.01, "0.99-1.0"), (0.90, 0.99, "0.90-0.99"),
         (0.50, 0.90, "0.50-0.90"), (0.0, 0.50, "below 0.50")]
labels, rates, counts = [], [], []
for lo, hi, name in bands:
    b = human[(human["static_probability"] >= lo)
              & (human["static_probability"] < hi)]
    if len(b):
        labels.append(name)
        rates.append(b["near_power_plant"].mean() * 100)
        counts.append(len(b))

bars = ax.bar(labels, rates, color=GREEN, width=0.6)
ax.axhline(base_rate * 100, color=RED, lw=1.3, ls=":",
           label=f"chance ({base_rate:.3%})")
for b, v, c in zip(bars, rates, counts):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.25,
            f"{v:.1f}%\n{c:,} places", ha="center", fontsize=8)
ax.set_xlabel("Model probability band")
ax.set_ylabel("% actually near a power plant")
ax.set_title("4.  Higher probability really does mean more likely")
ax.set_ylim(0, max(rates) * 1.35)
ax.legend(fontsize=8)

# ---- 5. Feature importance ------------------------------------------------
ax = axes[1][1]
bundle = joblib.load(MODEL_FILE)
model, feat_names = bundle["model"], bundle["features"]

feats = pd.read_csv(FEATURES_FILE)
feats = feats[feats["label"] >= 0]
sub = feats.sample(n=min(40_000, len(feats)), random_state=0)
imp = permutation_importance(
    model, sub[feat_names], sub["label"].astype(int),
    scoring="average_precision", n_repeats=3, random_state=42, n_jobs=1,
)
order = np.argsort(imp.importances_mean)[::-1][:10][::-1]
names10 = [feat_names[i] for i in order]
vals10 = imp.importances_mean[order]

ax.barh(names10, vals10, color=PURPLE, height=0.65)
for i, v in enumerate(vals10):
    ax.text(v + max(vals10) * 0.015, i, f"{v:.3f}", va="center", fontsize=8)
ax.set_xlabel("Drop in PR-AUC when this feature is shuffled")
ax.set_title("5.  Which clues the model actually uses")
ax.set_xlim(0, max(vals10) * 1.22)
ax.grid(axis="y", visible=False)

# ---- 6. v1 vs v2 ----------------------------------------------------------
ax = axes[1][2]
ax.axis("off")
ax.set_title("6.  Version 1 vs Version 2", loc="left")

rows = [
    ("", "v1  (detection)", "v2  (place)"),
    ("Unit", "one pixel", "one 5 km place"),
    ("Features", "9  (incl. lat/lon)", "19  (no coords)"),
    ("Validation", "random split", "held-out regions"),
    ("Reported score", "0.989 ROC-AUC", "0.902 PR-AUC"),
    ("Is it honest?", "NO - memorised map", "YES"),
    ("lat alone scores", "0.922 (!)", "not used"),
    ("Beats NASA label?", "no - copies it", "yes  15.3% vs 11.8%"),
    ("Volcanoes", "counted as industry", "flagged separately"),
]
for r, (a, b, c) in enumerate(rows):
    yy = 0.93 - r * 0.105
    weight = "bold" if r == 0 else "normal"
    ax.text(0.0, yy, a, fontsize=9, fontweight="bold", transform=ax.transAxes)
    ax.text(0.40, yy, b, fontsize=9, fontweight=weight, color=RED if r else INK,
            transform=ax.transAxes)
    ax.text(0.73, yy, c, fontsize=9, fontweight=weight,
            color=GREEN if r else INK, transform=ax.transAxes)
    if r == 0:
        ax.plot([0, 1], [yy - 0.035] * 2, color="#d4d4d4", lw=1,
                transform=ax.transAxes)

ax.text(0.0, -0.04,
        "v1's 0.989 was inflated by memorising where oil fields are.\n"
        "v2's 0.902 is measured on regions it had never seen.",
        fontsize=8.2, style="italic", color=MUTED, transform=ax.transAxes)

plt.tight_layout(rect=[0, 0.01, 1, 0.955])
OUT.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT, dpi=145, bbox_inches="tight", facecolor="white")

print(f"PR-AUC (out-of-fold, all places): {ap:.3f}")
print(f"Per-fold: {[round(v, 3) for v in fold_ap]}")
print(f"Saved chart to: {OUT}")
