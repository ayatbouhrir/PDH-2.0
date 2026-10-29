import os
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth, association_rules

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

DATA_FILE = "full.csv"
OUTPUT_DIR = "artifacts/experiments/fpgrowth"

MIN_SUPPORT_GLOBAL = 0.02
MIN_CONFIDENCE_GLOBAL = 0.60

MIN_SUPPORT_STRATIFIED = 0.05
MIN_CONFIDENCE_STRATIFIED = 0.60

MAX_RULE_LENGTH = 3
MIN_ROWS_PER_STRATE = 500

TOP_N_CATEGORIES = 50

COLS_KEEP = [
    "category",
    "country",
    "type",
    "sector",
    "source_type",
    "data_collection_method",
    "dataset_name",
    "matrix",
    "unit",
    "pfas_sum",
    "year"
]

STRATIFICATION_COLS = [
    "country",
    "category",
    "type",
    "source_type",
    "dataset_name",
    "matrix",
    "periode"
]

BAD_TERMS = [
    "inconnu",
    "unknown",
    "nan",
    "none",
    "null",
    "vide"
]


# ============================================================
# OUTILS
# ============================================================

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
    )
    return df


def clean_text(value):
    if pd.isna(value):
        return np.nan

    value = str(value).strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-zA-Z0-9_éèêàùçôîïâ]", "", value)

    if value in ["", "nan", "none", "null", "inconnu"]:
        return np.nan

    return value


def replace_fake_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    fake_missing = [
        "",
        " ",
        "nan",
        "NaN",
        "None",
        "none",
        "NULL",
        "null",
        "inconnu",
        "unknown"
    ]

    df = df.replace(fake_missing, np.nan)
    return df


def keep_top_categories(series: pd.Series, top_n: int = 50) -> pd.Series:
    top_values = series.dropna().value_counts().head(top_n).index
    return series.where(series.isna() | series.isin(top_values), "autre")


def contains_bad_item(itemset) -> bool:
    for item in itemset:
        item_str = str(item).lower()
        for term in BAD_TERMS:
            if term in item_str:
                return True
    return False


def format_itemset(itemset) -> str:
    return ", ".join([str(item).replace("_", " ") for item in itemset])


def save_dataframe(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Fichier sauvegardé : {path}")


# ============================================================
# PRÉPARATION DES DONNÉES
# ============================================================

def prepare_pfas_data(df: pd.DataFrame) -> pd.DataFrame:
    print("\n========== PRÉPARATION DES DONNÉES ==========")

    df_rules = df.copy()
    df_rules = clean_column_names(df_rules)

    print("Shape initial :", df_rules.shape)

    available_cols = [col for col in COLS_KEEP if col in df_rules.columns]
    df_rules = df_rules[available_cols].copy()

    print("Colonnes gardées :", available_cols)
    print("Shape après sélection :", df_rules.shape)

    df_rules = replace_fake_missing_values(df_rules)

    # --------------------------------------------------------
    # Filtrer les lignes avec vraie mesure PFAS
    # --------------------------------------------------------
    if "pfas_sum" in df_rules.columns:
        df_rules["pfas_sum"] = pd.to_numeric(df_rules["pfas_sum"], errors="coerce")

        before = len(df_rules)
        df_rules = df_rules[df_rules["pfas_sum"].notna()].copy()
        after = len(df_rules)

        print(f"Lignes avec pfas_sum réel : {after} / {before}")

        if after == 0:
            raise ValueError(
                "Aucune ligne avec pfas_sum réel. "
                "Vérifie la colonne pfas_sum dans full.csv."
            )

        # Discrétisation métier simple
        df_rules["pfas_sum_cat"] = pd.cut(
            df_rules["pfas_sum"],
            bins=[-np.inf, 0, 0.001, 0.01, 0.1, 1, np.inf],
            labels=[
                "zero",
                "trace",
                "tres_faible",
                "faible",
                "moyenne",
                "elevee"
            ]
        )

        df_rules = df_rules.drop(columns=["pfas_sum"])

    # --------------------------------------------------------
    # Transformer year en période
    # --------------------------------------------------------
    if "year" in df_rules.columns:
        df_rules["year"] = pd.to_numeric(df_rules["year"], errors="coerce")

        df_rules["periode"] = pd.cut(
            df_rules["year"],
            bins=[-np.inf, 2015, 2020, 2023, np.inf],
            labels=[
                "avant_2015",
                "2016_2020",
                "2021_2023",
                "apres_2023"
            ]
        )

        df_rules = df_rules.drop(columns=["year"])

    # --------------------------------------------------------
    # Convertir les catégories pandas en object
    # --------------------------------------------------------
    for col in df_rules.select_dtypes(include=["category"]).columns:
        df_rules[col] = df_rules[col].astype("object")

    # --------------------------------------------------------
    # Nettoyer les textes sans créer "inconnu"
    # --------------------------------------------------------
    for col in df_rules.columns:
        df_rules[col] = df_rules[col].apply(clean_text)

    # --------------------------------------------------------
    # Regrouper les valeurs rares
    # --------------------------------------------------------
    for col in df_rules.columns:
        df_rules[col] = keep_top_categories(df_rules[col], TOP_N_CATEGORIES)

    print("Shape final df_rules :", df_rules.shape)
    print("\nValeurs manquantes par colonne :")
    print(df_rules.isna().sum())

    return df_rules


# ============================================================
# TRANSACTIONS
# ============================================================

def build_transactions(df_rules: pd.DataFrame) -> pd.DataFrame:
    print("\n========== CONSTRUCTION DES TRANSACTIONS ==========")

    df_items = pd.DataFrame(index=df_rules.index)

    for col in df_rules.columns:
        df_items[col] = np.where(
            df_rules[col].notna(),
            col + "_" + df_rules[col].astype(str),
            np.nan
        )

    print("Shape df_items :", df_items.shape)

    transactions = pd.get_dummies(
        df_items,
        dummy_na=False,
        sparse=True,
        dtype=bool
    )

    print("Nombre de transactions :", transactions.shape[0])
    print("Nombre d'items :", transactions.shape[1])

    memory_mb = transactions.memory_usage(deep=True).sum() / 1024 ** 2
    print(f"Mémoire estimée transactions : {memory_mb:.2f} MB")

    return transactions


# ============================================================
# FP-GROWTH
# ============================================================

def run_fpgrowth(
    transactions: pd.DataFrame,
    min_support: float,
    min_confidence: float,
    max_len: int
) -> pd.DataFrame:

    if transactions.empty:
        return pd.DataFrame()

    frequent_itemsets = fpgrowth(
        transactions,
        min_support=min_support,
        use_colnames=True,
        max_len=max_len
    )

    if frequent_itemsets.empty:
        return pd.DataFrame()

    rules = association_rules(
        frequent_itemsets,
        metric="confidence",
        min_threshold=min_confidence
    )

    if rules.empty:
        return pd.DataFrame()

    rules = rules.sort_values(
        by=["lift", "confidence", "support"],
        ascending=False
    )

    rules = rules[
        ~rules["antecedents"].apply(contains_bad_item)
        &
        ~rules["consequents"].apply(contains_bad_item)
    ].copy()

    return rules


def make_rules_readable(rules: pd.DataFrame) -> pd.DataFrame:
    if rules.empty:
        return pd.DataFrame()

    readable = rules.copy()

    readable["SI"] = readable["antecedents"].apply(format_itemset)
    readable["ALORS"] = readable["consequents"].apply(format_itemset)

    readable["support_%"] = (readable["support"] * 100).round(2)
    readable["confidence_%"] = (readable["confidence"] * 100).round(2)
    readable["lift"] = readable["lift"].round(2)

    readable["interpretation"] = readable.apply(
        lambda row: (
            f"Si {row['SI']}, alors {row['ALORS']} "
            f"dans {row['confidence_%']}% des cas. "
            f"Support = {row['support_%']}%. "
            f"Lift = {row['lift']}."
        ),
        axis=1
    )

    final_cols = [
        "SI",
        "ALORS",
        "support_%",
        "confidence_%",
        "lift",
        "interpretation"
    ]

    return readable[final_cols].copy()


# ============================================================
# ANALYSE GLOBALE
# ============================================================

def global_analysis(df_rules: pd.DataFrame, output_dir: Path):
    print("\n========== FP-GROWTH GLOBAL ==========")

    transactions = build_transactions(df_rules)

    rules_global = run_fpgrowth(
        transactions=transactions,
        min_support=MIN_SUPPORT_GLOBAL,
        min_confidence=MIN_CONFIDENCE_GLOBAL,
        max_len=MAX_RULE_LENGTH
    )

    print("Nombre de règles globales :", len(rules_global))

    rules_global_readable = make_rules_readable(rules_global)

    if not rules_global_readable.empty:
        print("\nTop 20 règles globales :")
        print(rules_global_readable.head(20).to_string(index=False))

        save_dataframe(
            rules_global_readable,
            output_dir / "rules_global_readable.csv"
        )
    else:
        print("Aucune règle globale trouvée.")

    return rules_global_readable


# ============================================================
# ANALYSE STRATIFIÉE
# ============================================================

def stratified_analysis(df_rules: pd.DataFrame, output_dir: Path):
    print("\n========== FP-GROWTH STRATIFIÉ ==========")

    all_stratified_rules = []

    available_strata = [
        col for col in STRATIFICATION_COLS
        if col in df_rules.columns
    ]

    print("Colonnes de stratification disponibles :", available_strata)

    for strat_col in available_strata:
        print(f"\n--- Stratification par : {strat_col} ---")

        values = df_rules[strat_col].dropna().unique()

        for value in values:
            subset = df_rules[df_rules[strat_col] == value].copy()

            n_rows = len(subset)

            if n_rows < MIN_ROWS_PER_STRATE:
                continue

            print(f"Traitement strate {strat_col} = {value} | lignes = {n_rows}")

            transactions = build_transactions(subset)

            rules = run_fpgrowth(
                transactions=transactions,
                min_support=MIN_SUPPORT_STRATIFIED,
                min_confidence=MIN_CONFIDENCE_STRATIFIED,
                max_len=MAX_RULE_LENGTH
            )

            if rules.empty:
                continue

            readable = make_rules_readable(rules)

            if readable.empty:
                continue

            readable["strate_colonne"] = strat_col
            readable["strate_valeur"] = value
            readable["nb_lignes_strate"] = n_rows

            readable = readable[
                [
                    "strate_colonne",
                    "strate_valeur",
                    "nb_lignes_strate",
                    "SI",
                    "ALORS",
                    "support_%",
                    "confidence_%",
                    "lift",
                    "interpretation"
                ]
            ]

            all_stratified_rules.append(readable)

    if len(all_stratified_rules) == 0:
        print("Aucune règle stratifiée trouvée.")
        return pd.DataFrame()

    rules_stratified_readable = pd.concat(
        all_stratified_rules,
        ignore_index=True
    )

    rules_stratified_readable = rules_stratified_readable.sort_values(
        by=["lift", "confidence_%", "support_%"],
        ascending=False
    )

    print("\nNombre total de règles stratifiées :", len(rules_stratified_readable))

    print("\nTop 20 règles stratifiées :")
    print(rules_stratified_readable.head(20).to_string(index=False))

    save_dataframe(
        rules_stratified_readable,
        output_dir / "rules_stratified_readable.csv"
    )

    return rules_stratified_readable


# ============================================================
# RÉSUMÉ AUTOMATIQUE
# ============================================================

def generate_summary(
    df_original: pd.DataFrame,
    df_rules: pd.DataFrame,
    rules_global: pd.DataFrame,
    rules_stratified: pd.DataFrame,
    output_dir: Path
):
    summary_path = output_dir / "summary_fpgrowth.txt"

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("RÉSUMÉ FP-GROWTH PFAS\n")
        f.write("=====================\n\n")

        f.write(f"Shape dataset original : {df_original.shape}\n")
        f.write(f"Shape dataset préparé  : {df_rules.shape}\n\n")

        f.write("Colonnes utilisées :\n")
        for col in df_rules.columns:
            f.write(f"- {col}\n")

        f.write("\nParamètres globaux :\n")
        f.write(f"- min_support_global = {MIN_SUPPORT_GLOBAL}\n")
        f.write(f"- min_confidence_global = {MIN_CONFIDENCE_GLOBAL}\n")
        f.write(f"- max_rule_length = {MAX_RULE_LENGTH}\n\n")

        f.write("Paramètres stratifiés :\n")
        f.write(f"- min_support_stratified = {MIN_SUPPORT_STRATIFIED}\n")
        f.write(f"- min_confidence_stratified = {MIN_CONFIDENCE_STRATIFIED}\n")
        f.write(f"- min_rows_per_strate = {MIN_ROWS_PER_STRATE}\n\n")

        f.write(f"Nombre de règles globales : {len(rules_global)}\n")
        f.write(f"Nombre de règles stratifiées : {len(rules_stratified)}\n\n")

        if not rules_global.empty:
            f.write("TOP 10 RÈGLES GLOBALES :\n")
            for _, row in rules_global.head(10).iterrows():
                f.write(f"- {row['interpretation']}\n")

        if not rules_stratified.empty:
            f.write("\nTOP 10 RÈGLES STRATIFIÉES :\n")
            for _, row in rules_stratified.head(10).iterrows():
                f.write(
                    f"- Dans {row['strate_colonne']} = {row['strate_valeur']} : "
                    f"{row['interpretation']}\n"
                )

    print(f"Résumé sauvegardé : {summary_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    base_dir = Path(__file__).resolve().parents[2]
    data_path = base_dir / ".local" / DATA_FILE
    output_dir = base_dir / OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {data_path}\n"
            f"Place full.csv dans le dossier .local du projet."
        )

    print("Fichier utilisé :", data_path)
    print("Dossier résultats :", output_dir)

    # --------------------------------------------------------
    # Charger full.csv
    # --------------------------------------------------------
    df = pd.read_csv(data_path, low_memory=False)

    print("\nDataset chargé.")
    print("Shape :", df.shape)

    # --------------------------------------------------------
    # Préparer
    # --------------------------------------------------------
    df_rules = prepare_pfas_data(df)

    save_dataframe(
        df_rules,
        output_dir / "prepared_dataset_for_fpgrowth.csv"
    )

    # --------------------------------------------------------
    # Analyse globale
    # --------------------------------------------------------
    rules_global_readable = global_analysis(df_rules, output_dir)

    # --------------------------------------------------------
    # Analyse stratifiée
    # --------------------------------------------------------
    rules_stratified_readable = stratified_analysis(df_rules, output_dir)

    # --------------------------------------------------------
    # Résumé
    # --------------------------------------------------------
    generate_summary(
        df_original=df,
        df_rules=df_rules,
        rules_global=rules_global_readable,
        rules_stratified=rules_stratified_readable,
        output_dir=output_dir
    )

    elapsed = time.time() - start_time

    print("\n========== TERMINÉ ==========")
    print(f"Temps total : {elapsed / 60:.2f} minutes")
    print(f"Résultats dans : {output_dir}")


if __name__ == "__main__":
    main()
