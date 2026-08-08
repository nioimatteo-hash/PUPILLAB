#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import traceback
from pathlib import Path
from threading import Thread

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

APP_TITLE = "PIR Analisi Finale - GUI"
BG = "#101010"
PANEL = "#1d1d1d"
FG = "#f2f2f2"

# Soglie operative PIR richieste
MIOSI_MAX = 0.275
MIDRIASI_MIN = 0.460

# Soglie operative per le forme estreme
MIOSI_SEVERA_MAX = 0.200
MIDRIASI_SEVERA_MIN = 0.600

SUBSTANCE_MAP = {
    "opioids": {"MORFINA", "EROINA", "6-ACETILMORFINA", "METADONE", "TRAMADOLO"},
    "heroin_morphine_core": {"MORFINA", "EROINA", "6-ACETILMORFINA"},
    "methadone": {"METADONE"},
    "tramadol": {"TRAMADOLO"},
    "cocaine": {"COCAINA", "BENZOILECGONINA"},
    "benzodiazepines": {"ALPRAZOLAM", "DIAZEPAM", "LORAZEPAM", "MIDAZOLAM", "CLONAZEPAM", "DELORAZEPAM", "TEMAZEPAM", "OXAZEPAM", "NORDIAZEPAM"},
    "cannabis": {"THC", "THC-COOH", "CANNABIS"},
    "ethanol": {"ETANOLO"},
    "antipsychotics": {"CLORPROMAZINA", "QUIETAPINA", "OLANZAPINA", "ALOPERIDOLO", "RISPERIDONE"},
    "ketamine": {"KETAMINA"},
}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_col(x: str) -> str:
    x = str(x).strip().upper().replace("'", "")
    x = re.sub(r"[^A-Z0-9]+", "_", x)
    return x.strip("_")


def clean_numeric(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.replace(",", ".", regex=False)
    s = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(s, errors="coerce")


def classify_pir(x):
    if pd.isna(x):
        return np.nan
    try:
        x = float(x)
    except Exception:
        return np.nan
    if 0 <= x <= MIOSI_MAX:
        return "MIOSI"
    if MIOSI_MAX < x < MIDRIASI_MIN:
        return "INTERMEDIO"
    if x >= MIDRIASI_MIN:
        return "MIDRIASI"
    return "NON_CLASSIFICATO"


def safe_categorical(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.replace({"": np.nan, "nan": np.nan, "NAN": np.nan, "None": np.nan})
    return s


def save_text(obj, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(obj))


def ci95_or_from_model(result):
    params = result.params
    conf = result.conf_int()
    return pd.DataFrame({
        "term": params.index,
        "coef": params.values,
        "OR": np.exp(params.values),
        "CI95_LOW": np.exp(conf.iloc[:, 0].values),
        "CI95_HIGH": np.exp(conf.iloc[:, 1].values),
        "p_value": result.pvalues.values,
    })


def coeff_table_from_model(result):
    conf = result.conf_int()
    return pd.DataFrame({
        "term": result.params.index,
        "beta": result.params.values,
        "CI95_LOW": conf.iloc[:, 0].values,
        "CI95_HIGH": conf.iloc[:, 1].values,
        "p_value": result.pvalues.values,
    })


def maybe_import_sklearn_metrics():
    try:
        from sklearn.metrics import roc_curve, auc  # type: ignore
        return roc_curve, auc
    except Exception:
        return None, None


class PIRAnalysis:
    def __init__(self, input_file, output_dir, logger=None):
        self.input_file = Path(input_file)
        self.output_dir = ensure_dir(Path(output_dir))
        self.log = logger if logger else print
        self.df = None
        self.eye_df = None
        self.dirs = {}

    def _msg(self, text: str):
        self.log(text)

    def build_dirs(self):
        names = [
            "00_qc",
            "01_descriptives",
            "02_binary_models",
            "03_continuous_models",
            "04_asymmetry",
            "05_causes",
            "06_substance_models",
            "07_roc_quantile",
            "08_reports",
        ]
        self.dirs = {n: ensure_dir(self.output_dir / n) for n in names}

    def load(self):
        self._msg("Caricamento file Excel...")
        df = pd.read_excel(self.input_file)
        df.columns = [normalize_col(c) for c in df.columns]

        ren = {}
        if "ETA_" in df.columns and "ETA" not in df.columns:
            ren["ETA_"] = "ETA"
        if "NUMERO_CAS" in df.columns and "NUMERO_CASO" not in df.columns:
            ren["NUMERO_CAS"] = "NUMERO_CASO"
        if ren:
            df = df.rename(columns=ren)

        if "NUMERO_CASO" not in df.columns:
            df["NUMERO_CASO"] = np.arange(1, len(df) + 1)

        required = ["NUMERO_CASO", "ETA", "SESSO", "PMI", "PIR_OD", "PIR_OS"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Colonne mancanti: {missing}")

        for c in ["ETA", "PMI", "PIR_OD", "PIR_OS"]:
            df[c] = clean_numeric(df[c])

        df["SESSO"] = df["SESSO"].astype(str).str.upper().str.strip()

        for c in ["CAUSA_DI_MORTE", "CATEGORIA_DI_MORTE", "CAUSA_DI_MORTE_FIX", "CATEGORIA_DI_MORTE_FIX"]:
            if c not in df.columns:
                df[c] = np.nan
            df[c] = safe_categorical(df[c])

        for c in ["SOSTANZA1", "SOSTANZA2", "SOSTANZA3"]:
            if c not in df.columns:
                df[c] = np.nan
            df[c] = df[c].astype(str).str.upper().str.strip().replace({"": np.nan, "NAN": np.nan, "NONE": np.nan, "nan": np.nan})

        df = df[df["PIR_OD"].notna() | df["PIR_OS"].notna()].copy().reset_index(drop=True)

        df["MEAN_PIR"] = df[["PIR_OD", "PIR_OS"]].mean(axis=1)
        df["MIN_PIR"] = df[["PIR_OD", "PIR_OS"]].min(axis=1)
        df["MAX_PIR"] = df[["PIR_OD", "PIR_OS"]].max(axis=1)
        df["CLASSIFICAZIONE_OD"] = df["PIR_OD"].apply(classify_pir)
        df["CLASSIFICAZIONE_OS"] = df["PIR_OS"].apply(classify_pir)
        df["CLASSIFICAZIONE_MEAN"] = df["MEAN_PIR"].apply(classify_pir)
        df["MIOSI_CASE"] = (df["MIN_PIR"] <= MIOSI_MAX).astype(int)
        df["MIDRIASI_CASE"] = (df["MAX_PIR"] >= MIDRIASI_MIN).astype(int)
        df["MIOSI_SEVERA_CASE"] = (df["MIN_PIR"] <= MIOSI_SEVERA_MAX).astype(int)
        df["MIDRIASI_SEVERA_CASE"] = (df["MAX_PIR"] >= MIDRIASI_SEVERA_MIN).astype(int)
        df["DELTA_PIR_ABS"] = (df["PIR_OD"] - df["PIR_OS"]).abs()
        df["ASYM_GT_10PCT"] = (df["DELTA_PIR_ABS"] > 0.10).astype(int)
        df["ETA2"] = df["ETA"] ** 2

        df["SUBSTANCE_COUNT"] = df[["SOSTANZA1", "SOSTANZA2", "SOSTANZA3"]].notna().sum(axis=1)
        df["NO_SUBSTANCE"] = (df["SUBSTANCE_COUNT"] == 0).astype(int)
        df["ANY_SUBSTANCE"] = (df["SUBSTANCE_COUNT"] > 0).astype(int)

        for key, subs in SUBSTANCE_MAP.items():
            df[key] = df[["SOSTANZA1", "SOSTANZA2", "SOSTANZA3"]].apply(
                lambda r: int(any(x in subs for x in r.dropna().tolist())), axis=1
            )

        df["OPIOIDS_ONLY"] = ((df["opioids"] == 1) & (df["SUBSTANCE_COUNT"] == 1)).astype(int)
        df["OPIOIDS_MIXED"] = ((df["opioids"] == 1) & (df["SUBSTANCE_COUNT"] >= 2)).astype(int)
        df["OTHER_DRUGS_ONLY"] = ((df["opioids"] == 0) & (df["ANY_SUBSTANCE"] == 1)).astype(int)

        def define_group(r):
            if r["OPIOIDS_ONLY"] == 1:
                return "OPPIOIDI_PURI"
            if r["OPIOIDS_MIXED"] == 1:
                return "OPPIOIDI_MISTI"
            if r["OTHER_DRUGS_ONLY"] == 1:
                return "ALTRE_DROGHE"
            if r["NO_SUBSTANCE"] == 1:
                return "NON_ASSUNTORI"
            return "ALTRO"

        df["GRUPPO"] = df.apply(define_group, axis=1)
        df["GRUPPO"] = pd.Categorical(
            df["GRUPPO"],
            categories=["NON_ASSUNTORI", "ALTRE_DROGHE", "OPPIOIDI_MISTI", "OPPIOIDI_PURI"],
        )

        rows = []
        for _, r in df.iterrows():
            cause_use = r.get("CATEGORIA_DI_MORTE_FIX")
            if pd.isna(cause_use):
                cause_use = r.get("CAUSA_DI_MORTE_FIX")
            if pd.isna(cause_use):
                cause_use = r.get("CATEGORIA_DI_MORTE")
            if pd.isna(cause_use):
                cause_use = r.get("CAUSA_DI_MORTE")

            for eye in ("OD", "OS"):
                pir = r[f"PIR_{eye}"]
                if pd.notna(pir):
                    rows.append({
                        "ID": r["NUMERO_CASO"],
                        "EYE": eye,
                        "PIR": float(pir),
                        "ETA": r["ETA"],
                        "ETA2": r["ETA2"],
                        "PMI": r["PMI"],
                        "SESSO": r["SESSO"],
                        "CAUSA": cause_use,
                        "GRUPPO": r["GRUPPO"],
                        "MIOSI": int(0 <= float(pir) <= MIOSI_MAX),
                        "INTERMEDIO": int(MIOSI_MAX < float(pir) < MIDRIASI_MIN),
                        "MIDRIASI": int(float(pir) >= MIDRIASI_MIN),
                        "MIOSI_SEVERA": int(float(pir) <= MIOSI_SEVERA_MAX),
                        "MIDRIASI_SEVERA": int(float(pir) >= MIDRIASI_SEVERA_MIN),
                        "opioids": r["opioids"],
                        "cocaine": r["cocaine"],
                        "ethanol": r["ethanol"],
                        "benzodiazepines": r["benzodiazepines"],
                        "ketamine": r["ketamine"],
                        "antipsychotics": r["antipsychotics"],
                        "cannabis": r["cannabis"],
                        "ANY_SUBSTANCE": r["ANY_SUBSTANCE"],
                    })

        eye_df = pd.DataFrame(rows)
        eye_df["GRUPPO"] = pd.Categorical(
            eye_df["GRUPPO"],
            categories=["NON_ASSUNTORI", "ALTRE_DROGHE", "OPPIOIDI_MISTI", "OPPIOIDI_PURI"],
        )

        # Remove category levels with no observations. Keeping an empty level
        # creates an all-zero dummy column in formula-based models and can make
        # the design matrix singular (e.g. when no OPPIOIDI_PURI are present).
        df["GRUPPO"] = df["GRUPPO"].cat.remove_unused_categories()
        eye_df["GRUPPO"] = eye_df["GRUPPO"].cat.remove_unused_categories()

        self.df = df
        self.eye_df = eye_df

        pd.DataFrame([{
            "N_SOGGETTI": len(df),
            "N_OCCHI": len(eye_df),
            "N_OD_VALIDI": int(df["PIR_OD"].notna().sum()),
            "N_OS_VALIDI": int(df["PIR_OS"].notna().sum()),
            "N_ANY_SUBSTANCE": int(df["ANY_SUBSTANCE"].sum()),
            "N_OPIOIDS": int(df["opioids"].sum()),
            "N_COCAINE": int(df["cocaine"].sum()),
            "N_ETHANOL": int(df["ethanol"].sum()),
        }]).to_excel(self.dirs["00_qc"] / "qc_counts.xlsx", index=False)

        self._msg(f"Soggetti inclusi: {len(df)}")
        self._msg(f"Occhi inclusi: {len(eye_df)}")

    def save_descriptives(self):
        self._msg("Salvataggio descrittive...")
        subj = self.df.copy()
        eye = self.eye_df.copy()

        pd.DataFrame([{
            "N_SOGGETTI": len(subj),
            "N_OCCHI": len(eye),
            "ETA_MEAN": subj["ETA"].mean(),
            "ETA_SD": subj["ETA"].std(ddof=1),
            "PMI_MEAN": subj["PMI"].mean(),
            "PMI_SD": subj["PMI"].std(ddof=1),
            "MEAN_PIR_MEAN": subj["MEAN_PIR"].mean(),
            "MEAN_PIR_SD": subj["MEAN_PIR"].std(ddof=1),
            "MIN_PIR_MEAN": subj["MIN_PIR"].mean(),
            "MAX_PIR_MEAN": subj["MAX_PIR"].mean(),
            "MIOSI_CASE_PCT": 100 * subj["MIOSI_CASE"].mean(),
            "MIDRIASI_CASE_PCT": 100 * subj["MIDRIASI_CASE"].mean(),
            "MIOSI_SEVERA_CASE_PCT": 100 * subj["MIOSI_SEVERA_CASE"].mean(),
            "MIDRIASI_SEVERA_CASE_PCT": 100 * subj["MIDRIASI_SEVERA_CASE"].mean(),
            "ASYM_GT10_PCT": 100 * subj["ASYM_GT_10PCT"].mean(),
        }]).round(4).to_excel(self.dirs["01_descriptives"] / "summary.xlsx", index=False)

        pd.crosstab(eye["GRUPPO"], eye["MIOSI"]).to_excel(self.dirs["01_descriptives"] / "miosi_freq_eyelevel.xlsx")
        pd.crosstab(eye["GRUPPO"], eye["INTERMEDIO"]).to_excel(self.dirs["01_descriptives"] / "intermedio_freq_eyelevel.xlsx")
        pd.crosstab(eye["GRUPPO"], eye["MIDRIASI"]).to_excel(self.dirs["01_descriptives"] / "midriasi_freq_eyelevel.xlsx")
        pd.crosstab(eye["GRUPPO"], eye["MIOSI_SEVERA"]).to_excel(self.dirs["01_descriptives"] / "miosi_severa_freq_eyelevel.xlsx")
        pd.crosstab(eye["GRUPPO"], eye["MIDRIASI_SEVERA"]).to_excel(self.dirs["01_descriptives"] / "midriasi_severa_freq_eyelevel.xlsx")

        grp = eye.groupby("GRUPPO", observed=False).agg(
            N_EYES=("ID", "size"),
            N_SUBJECTS=("ID", "nunique"),
            PIR_MEAN=("PIR", "mean"),
            PIR_SD=("PIR", "std"),
            PIR_MEDIAN=("PIR", "median"),
            PIR_Q1=("PIR", lambda x: x.quantile(0.25)),
            PIR_Q3=("PIR", lambda x: x.quantile(0.75)),
            MIOSI_PCT=("MIOSI", lambda x: 100 * x.mean()),
            INTERMEDIO_PCT=("INTERMEDIO", lambda x: 100 * x.mean()),
            MIDRIASI_PCT=("MIDRIASI", lambda x: 100 * x.mean()),
            MIOSI_SEVERA_PCT=("MIOSI_SEVERA", lambda x: 100 * x.mean()),
            MIDRIASI_SEVERA_PCT=("MIDRIASI_SEVERA", lambda x: 100 * x.mean()),
        ).reset_index().round(4)
        grp.to_excel(self.dirs["01_descriptives"] / "group_descriptives_eyelevel.xlsx", index=False)

        substance_desc = subj.groupby("GRUPPO", observed=False).agg(
            N_CASES=("NUMERO_CASO", "size"),
            ANY_SUBSTANCE_PCT=("ANY_SUBSTANCE", lambda x: 100 * x.mean()),
            OPIOIDS_PCT=("opioids", lambda x: 100 * x.mean()),
            COCAINE_PCT=("cocaine", lambda x: 100 * x.mean()),
            ETHANOL_PCT=("ethanol", lambda x: 100 * x.mean()),
            BENZO_PCT=("benzodiazepines", lambda x: 100 * x.mean()),
            KETAMINE_PCT=("ketamine", lambda x: 100 * x.mean()),
            ANTIPSYCH_PCT=("antipsychotics", lambda x: 100 * x.mean()),
        ).reset_index().round(4)
        substance_desc.to_excel(self.dirs["01_descriptives"] / "substance_prevalence_by_group.xlsx", index=False)

        self.df.to_excel(self.dirs["01_descriptives"] / "subject_level_clean.xlsx", index=False)
        self.eye_df.to_excel(self.dirs["01_descriptives"] / "eye_level_long.xlsx", index=False)

    def gee_binary(self, outcome, filename_prefix, predictors=None, data=None):
        self._msg(f"Modello GEE binario: {outcome} ...")
        dat = self.eye_df.copy() if data is None else data.copy()
        default_predictors = "C(GRUPPO, Treatment('NON_ASSUNTORI')) + ETA + PMI"
        predictors = predictors or default_predictors
        dat = dat.dropna(subset=[outcome, "ETA", "PMI"]).copy()
        model = smf.gee(
            f"{outcome} ~ {predictors}",
            groups="ID",
            data=dat,
            family=sm.families.Binomial(),
            cov_struct=sm.cov_struct.Exchangeable(),
        )
        result = model.fit()
        save_text(result.summary(), self.dirs["02_binary_models"] / f"{filename_prefix}_summary.txt")
        ci95_or_from_model(result).to_excel(self.dirs["02_binary_models"] / f"{filename_prefix}_OR_IC95.xlsx", index=False)

    def fit_lmm_or_cluster_ols(self, formula, dat, groups_col, base_name, subdir="03_continuous_models"):
        try:
            model = smf.mixedlm(formula, dat, groups=dat[groups_col])
            result = model.fit(reml=False, method="lbfgs")
            save_text(result.summary(), self.dirs[subdir] / f"{base_name}_mixedlm_summary.txt")
            coeff_table_from_model(result).to_excel(self.dirs[subdir] / f"{base_name}_mixedlm_coefficients.xlsx", index=False)
            self._msg(f"{base_name}: MixedLM riuscito")
            return result
        except Exception:
            save_text(traceback.format_exc(), self.dirs[subdir] / f"{base_name}_mixedlm_error.txt")
            self._msg(f"{base_name}: MixedLM fallito, uso OLS cluster-robust")
            ols = smf.ols(formula, data=dat).fit(cov_type="cluster", cov_kwds={"groups": dat[groups_col]})
            save_text(ols.summary(), self.dirs[subdir] / f"{base_name}_clusterOLS_summary.txt")
            coeff_table_from_model(ols).to_excel(self.dirs[subdir] / f"{base_name}_clusterOLS_coefficients.xlsx", index=False)
            return ols

    def continuous_models(self):
        self._msg("Modelli continui PIR...")
        dat = self.eye_df.dropna(subset=["PIR", "GRUPPO", "ETA", "PMI"]).copy()
        self.fit_lmm_or_cluster_ols(
            "PIR ~ C(GRUPPO, Treatment('NON_ASSUNTORI')) + ETA + PMI + C(EYE)",
            dat, "ID", "pir_main"
        )
        self.fit_lmm_or_cluster_ols(
            "PIR ~ ETA + C(EYE)",
            self.eye_df.dropna(subset=["PIR", "ETA"]).copy(), "ID", "pir_vs_eta"
        )
        self.fit_lmm_or_cluster_ols(
            "PIR ~ PMI + C(EYE)",
            self.eye_df.dropna(subset=["PIR", "PMI"]).copy(), "ID", "pir_vs_pmi"
        )
        self.fit_lmm_or_cluster_ols(
            "PIR ~ ETA + ETA2 + PMI + C(EYE)",
            self.eye_df.dropna(subset=["PIR", "ETA", "ETA2", "PMI"]).copy(), "ID", "pir_eta_nonlinear"
        )

    def asymmetry_models(self):
        self._msg("Analisi asimmetria...")
        dat = self.df.dropna(subset=["DELTA_PIR_ABS", "GRUPPO", "ETA", "PMI"]).copy()
        ols = smf.ols(
            "DELTA_PIR_ABS ~ C(GRUPPO, Treatment('NON_ASSUNTORI')) + ETA + PMI",
            data=dat
        ).fit(cov_type="HC3")
        save_text(ols.summary(), self.dirs["04_asymmetry"] / "delta_ols_summary.txt")
        coeff_table_from_model(ols).to_excel(self.dirs["04_asymmetry"] / "delta_ols_coefficients.xlsx", index=False)

        try:
            logit = smf.logit(
                "ASYM_GT_10PCT ~ C(GRUPPO, Treatment('NON_ASSUNTORI')) + ETA + PMI",
                data=dat
            ).fit(disp=False)
            save_text(logit.summary(), self.dirs["04_asymmetry"] / "asym_gt10_logit_summary.txt")
            ci95_or_from_model(logit).to_excel(self.dirs["04_asymmetry"] / "asym_gt10_OR_IC95.xlsx", index=False)
        except Exception:
            save_text(traceback.format_exc(), self.dirs["04_asymmetry"] / "asym_gt10_logit_error.txt")

        dat[["NUMERO_CASO", "PIR_OD", "PIR_OS", "DELTA_PIR_ABS", "ASYM_GT_10PCT", "GRUPPO"]].to_excel(
            self.dirs["04_asymmetry"] / "asymmetry_subject_table.xlsx", index=False
        )

    def cause_models(self):
        self._msg("Analisi cause di morte...")
        dat = self.eye_df.dropna(subset=["PIR", "CAUSA", "ETA", "PMI"]).copy()
        counts = dat["CAUSA"].value_counts()
        keep = counts[counts >= 4].index
        dat = dat[dat["CAUSA"].isin(keep)].copy()

        by = dat.groupby("CAUSA").agg(
            N_EYES=("ID", "size"),
            N_SUBJECTS=("ID", "nunique"),
            PIR_MEAN=("PIR", "mean"),
            PIR_SD=("PIR", "std"),
            PIR_MEDIAN=("PIR", "median"),
            PIR_Q1=("PIR", lambda x: x.quantile(0.25)),
            PIR_Q3=("PIR", lambda x: x.quantile(0.75)),
            MIOSI_PCT=("MIOSI", lambda x: 100 * x.mean()),
            INTERMEDIO_PCT=("INTERMEDIO", lambda x: 100 * x.mean()),
            MIDRIASI_PCT=("MIDRIASI", lambda x: 100 * x.mean()),
            MIOSI_SEVERA_PCT=("MIOSI_SEVERA", lambda x: 100 * x.mean()),
            MIDRIASI_SEVERA_PCT=("MIDRIASI_SEVERA", lambda x: 100 * x.mean()),
            ETA_MEAN=("ETA", "mean"),
            PMI_MEAN=("PMI", "mean"),
        ).reset_index().sort_values("N_EYES", ascending=False).round(4)
        by.to_excel(self.dirs["05_causes"] / "cause_descriptives.xlsx", index=False)

        if dat["CAUSA"].nunique() >= 2:
            self.fit_lmm_or_cluster_ols(
                "PIR ~ C(CAUSA) + ETA + PMI + C(EYE)",
                dat, "ID", "cause_pir", subdir="05_causes"
            )
            try:
                gee = smf.gee(
                    "MIOSI ~ C(CAUSA) + ETA + PMI",
                    groups="ID",
                    data=dat,
                    family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable(),
                ).fit()
                save_text(gee.summary(), self.dirs["05_causes"] / "cause_gee_miosi_summary.txt")
                ci95_or_from_model(gee).to_excel(self.dirs["05_causes"] / "cause_gee_miosi_OR_IC95.xlsx", index=False)
            except Exception:
                save_text(traceback.format_exc(), self.dirs["05_causes"] / "cause_gee_miosi_error.txt")
            try:
                gee = smf.gee(
                    "MIDRIASI ~ C(CAUSA) + ETA + PMI",
                    groups="ID",
                    data=dat,
                    family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable(),
                ).fit()
                save_text(gee.summary(), self.dirs["05_causes"] / "cause_gee_midriasi_summary.txt")
                ci95_or_from_model(gee).to_excel(self.dirs["05_causes"] / "cause_gee_midriasi_OR_IC95.xlsx", index=False)
            except Exception:
                save_text(traceback.format_exc(), self.dirs["05_causes"] / "cause_gee_midriasi_error.txt")

    def substance_specific_models(self):
        self._msg("Analisi per singole sostanze...")
        dat = self.eye_df.dropna(subset=["PIR", "ETA", "PMI"]).copy()

        # Modello continuo principale per classi di sostanza
        self.fit_lmm_or_cluster_ols(
            "PIR ~ opioids + cocaine + ethanol + benzodiazepines + ketamine + antipsychotics + ETA + PMI + C(EYE)",
            dat, "ID", "pir_substances", subdir="06_substance_models"
        )

        # MIOSI e MIDRIASI per sostanze specifiche
        for outcome, name in [
            ("MIOSI", "gee_miosi_substances"),
            ("MIDRIASI", "gee_midriasi_substances"),
            ("MIOSI_SEVERA", "gee_miosi_severa_substances"),
            ("MIDRIASI_SEVERA", "gee_midriasi_severa_substances"),
        ]:
            try:
                model = smf.gee(
                    f"{outcome} ~ opioids + cocaine + ethanol + benzodiazepines + ketamine + antipsychotics + ETA + PMI",
                    groups="ID",
                    data=dat,
                    family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable(),
                ).fit()
                save_text(model.summary(), self.dirs["06_substance_models"] / f"{name}_summary.txt")
                ci95_or_from_model(model).to_excel(self.dirs["06_substance_models"] / f"{name}_OR_IC95.xlsx", index=False)
            except Exception:
                save_text(traceback.format_exc(), self.dirs["06_substance_models"] / f"{name}_error.txt")

        # Interazione oppioidi*cocaina sul PIR continuo
        self.fit_lmm_or_cluster_ols(
            "PIR ~ opioids * cocaine + ethanol + benzodiazepines + ketamine + antipsychotics + ETA + PMI + C(EYE)",
            dat, "ID", "pir_interaction_opioids_cocaine", subdir="06_substance_models"
        )

        # Interazione oppioidi*cocaina su miosi e midriasi
        for outcome, name in [
            ("MIOSI", "gee_miosi_interaction_opioids_cocaine"),
            ("MIDRIASI", "gee_midriasi_interaction_opioids_cocaine"),
        ]:
            try:
                model = smf.gee(
                    f"{outcome} ~ opioids * cocaine + ethanol + ETA + PMI",
                    groups="ID",
                    data=dat,
                    family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable(),
                ).fit()
                save_text(model.summary(), self.dirs["06_substance_models"] / f"{name}_summary.txt")
                ci95_or_from_model(model).to_excel(self.dirs["06_substance_models"] / f"{name}_OR_IC95.xlsx", index=False)
            except Exception:
                save_text(traceback.format_exc(), self.dirs["06_substance_models"] / f"{name}_error.txt")

        # Analisi stratificate: solo tossicologici e solo non tossicologici
        dat_tox = dat[dat["ANY_SUBSTANCE"] == 1].copy()
        dat_notox = dat[dat["ANY_SUBSTANCE"] == 0].copy()

        if len(dat_tox) >= 10 and dat_tox["ID"].nunique() >= 5:
            self.fit_lmm_or_cluster_ols(
                "PIR ~ opioids + cocaine + ethanol + benzodiazepines + ketamine + antipsychotics + ETA + PMI + C(EYE)",
                dat_tox, "ID", "pir_substances_tox_only", subdir="06_substance_models"
            )

        if len(dat_notox) >= 10 and dat_notox["ID"].nunique() >= 5:
            self.fit_lmm_or_cluster_ols(
                "PIR ~ ETA + ETA2 + PMI + C(EYE)",
                dat_notox, "ID", "pir_notox_only", subdir="06_substance_models"
            )

    def roc_analysis(self):
        self._msg("ROC analysis...")
        roc_curve, auc = maybe_import_sklearn_metrics()
        if roc_curve is None:
            save_text("scikit-learn non disponibile: ROC non eseguita.", self.dirs["07_roc_quantile"] / "roc_unavailable.txt")
            return

        dat = self.eye_df.dropna(subset=["PIR", "opioids", "cocaine", "ANY_SUBSTANCE"]).copy()
        roc_specs = [
            ("opioids", "roc_opioids", -1),
            ("cocaine", "roc_cocaine", 1),
            ("ANY_SUBSTANCE", "roc_any_substance", -1),
        ]

        for outcome, base_name, direction in roc_specs:
            y = dat[outcome].astype(int)
            if y.nunique() < 2:
                save_text(f"Outcome {outcome} con una sola classe: ROC non calcolabile.", self.dirs["07_roc_quantile"] / f"{base_name}.txt")
                continue
            score = -dat["PIR"] if direction == -1 else dat["PIR"]
            fpr, tpr, thresholds = roc_curve(y, score)
            roc_auc = auc(fpr, tpr)
            pd.DataFrame({
                "FPR": fpr,
                "TPR": tpr,
                "THRESHOLD": thresholds,
            }).to_excel(self.dirs["07_roc_quantile"] / f"{base_name}.xlsx", index=False)
            save_text(f"AUC: {roc_auc:.4f}", self.dirs["07_roc_quantile"] / f"{base_name}.txt")

    def quantile_analysis(self):
        self._msg("Quantile regression...")
        dat = self.eye_df.dropna(subset=["PIR", "GRUPPO", "ETA", "PMI"]).copy()
        mod = smf.quantreg(
            "PIR ~ C(GRUPPO, Treatment('NON_ASSUNTORI')) + ETA + PMI + C(EYE)",
            dat
        )
        for q in [0.25, 0.50, 0.75]:
            try:
                res = mod.fit(q=q)
                suffix = str(q).replace(".", "")
                save_text(res.summary(), self.dirs["07_roc_quantile"] / f"quantile_{suffix}_summary.txt")
                coeff_table_from_model(res).to_excel(self.dirs["07_roc_quantile"] / f"quantile_{suffix}_coefficients.xlsx", index=False)
            except Exception:
                suffix = str(q).replace(".", "")
                save_text(traceback.format_exc(), self.dirs["07_roc_quantile"] / f"quantile_{suffix}_error.txt")

    def report(self):
        subj = self.df
        eye = self.eye_df
        txt = []
        txt.append(f"SOGGETTI INCLUSI: {len(subj)}")
        txt.append(f"OCCHI INCLUSI: {len(eye)}")
        txt.append(f"ETA media: {subj['ETA'].mean():.2f}")
        txt.append(f"PMI media: {subj['PMI'].mean():.2f}")
        txt.append(f"PIR medio soggetto: {subj['MEAN_PIR'].mean():.4f}")
        txt.append(f"Miosi case-level (<= {MIOSI_MAX}): {100 * subj['MIOSI_CASE'].mean():.1f}%")
        txt.append(f"Midriasi case-level (>= {MIDRIASI_MIN}): {100 * subj['MIDRIASI_CASE'].mean():.1f}%")
        txt.append(f"Miosi severa case-level (<= {MIOSI_SEVERA_MAX}): {100 * subj['MIOSI_SEVERA_CASE'].mean():.1f}%")
        txt.append(f"Midriasi severa case-level (>= {MIDRIASI_SEVERA_MIN}): {100 * subj['MIDRIASI_SEVERA_CASE'].mean():.1f}%")
        txt.append(f"Asimmetria >0.10: {100 * subj['ASYM_GT_10PCT'].mean():.1f}%")
        txt.append("")
        txt.append("NOTE:")
        txt.append("- MIOSI = PIR <= 0.275")
        txt.append("- INTERMEDIO = 0.275 < PIR < 0.460")
        txt.append("- MIDRIASI = PIR >= 0.460")
        txt.append("- Forme estreme: miosi estrema <=0.200; midriasi estrema >=0.600")
        save_text("\n".join(txt), self.dirs["08_reports"] / "quick_report.txt")

    def run_all(self):
        self.build_dirs()
        self.load()
        self.save_descriptives()
        self.gee_binary("MIOSI", "gee_miosi")
        self.gee_binary("MIDRIASI", "gee_midriasi")
        self.gee_binary("MIOSI_SEVERA", "gee_miosi_severa")
        self.gee_binary("MIDRIASI_SEVERA", "gee_midriasi_severa")
        self.continuous_models()
        self.asymmetry_models()
        self.cause_models()
        self.substance_specific_models()
        self.roc_analysis()
        self.quantile_analysis()
        self.report()
        self._msg("Analisi completata.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x780")
        self.configure(bg=BG)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.running = False
        self._build_ui()

    def _style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=BG, foreground=FG, font=("Segoe UI", 16, "bold"))

    def _build_ui(self):
        self._style()
        head = ttk.Frame(self)
        head.pack(fill="x", padx=12, pady=12)
        ttk.Label(head, text="PIR Analisi Finale - GUI", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            head,
            text=(
                "Occhio-level, GEE binaria, MixedLM con fallback OLS cluster-robust, "
                "asimmetria, cause di morte, sostanze specifiche, interazioni, ROC e quantili."
            ),
        ).pack(anchor="w", pady=(6, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        box = ttk.LabelFrame(left, text="Input e output")
        box.pack(fill="x", pady=8)
        ttk.Label(box, text="File input (.xlsx)").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.input_var, width=52).grid(row=1, column=0, padx=8, pady=4)
        ttk.Button(box, text="Sfoglia file", command=self.pick_input).grid(row=1, column=1, padx=8, pady=4)
        ttk.Label(box, text="Cartella output").grid(row=2, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.output_var, width=52).grid(row=3, column=0, padx=8, pady=4)
        ttk.Button(box, text="Sfoglia cartella", command=self.pick_output).grid(row=3, column=1, padx=8, pady=4)

        info = ttk.LabelFrame(left, text="Analisi incluse")
        info.pack(fill="x", pady=8)
        for t in [
            "1. QC + conteggio soggetti/occhi",
            "2. Descrittive soggetto e occhio",
            "3. GEE MIOSI/MIDRIASI + forme severe",
            "4. PIR continuo: MixedLM con fallback OLS cluster",
            "5. PIR vs ETA, PMI e modello età non lineare",
            "6. Asimmetria interoculare",
            "7. Cause di morte/categoria",
            "8. Sostanze specifiche e interazioni",
            "9. ROC per oppioidi/cocaina/sostanze",
            "10. Regressione quantilica",
            "11. Output Excel + TXT",
        ]:
            ttk.Label(info, text=t).pack(anchor="w", padx=8, pady=3)

        thr = ttk.LabelFrame(left, text="Soglie")
        thr.pack(fill="x", pady=8)
        ttk.Label(thr, text="MIOSI = PIR <= 0.275").pack(anchor="w", padx=8, pady=3)
        ttk.Label(thr, text="INTERMEDIO = 0.275 < PIR < 0.460").pack(anchor="w", padx=8, pady=3)
        ttk.Label(thr, text="MIDRIASI = PIR >= 0.460").pack(anchor="w", padx=8, pady=3)
        ttk.Label(thr, text="MIOSI ESTREMA = PIR <= 0.200").pack(anchor="w", padx=8, pady=3)
        ttk.Label(thr, text="MIDRIASI ESTREMA = PIR >= 0.600").pack(anchor="w", padx=8, pady=3)

        self.run_btn = ttk.Button(left, text="Esegui analisi", command=self.start_run)
        self.run_btn.pack(fill="x", padx=4, pady=10)
        self.progress = ttk.Progressbar(left, mode="indeterminate")
        self.progress.pack(fill="x", padx=4, pady=4)

        log_box = ttk.LabelFrame(right, text="Log")
        log_box.pack(fill="both", expand=True)
        self.log_widget = scrolledtext.ScrolledText(
            log_box,
            wrap="word",
            bg="#0f0f0f",
            fg="#eaeaea",
            insertbackground="#ffffff",
            font=("Consolas", 10),
        )
        self.log_widget.pack(fill="both", expand=True, padx=8, pady=8)
        self.write_log("Pronto. Seleziona input e output, poi avvia l'analisi.\n")

    def write_log(self, text):
        self.log_widget.insert("end", text + ("" if text.endswith("\n") else "\n"))
        self.log_widget.see("end")
        self.update_idletasks()

    def pick_input(self):
        p = filedialog.askopenfilename(title="Seleziona dataset", filetypes=[("Excel", "*.xlsx *.xls"), ("All files", "*.*")])
        if p:
            self.input_var.set(p)
            if not self.output_var.get():
                self.output_var.set(str(Path(p).with_suffix("").parent / f"{Path(p).stem}_OUTPUT"))

    def pick_output(self):
        p = filedialog.askdirectory(title="Seleziona cartella output")
        if p:
            self.output_var.set(p)

    def start_run(self):
        if self.running:
            return
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if not inp:
            messagebox.showerror(APP_TITLE, "Seleziona il file input.")
            return
        if not out:
            messagebox.showerror(APP_TITLE, "Seleziona la cartella output.")
            return
        self.running = True
        self.run_btn.config(state="disabled")
        self.progress.start(10)
        self.write_log("Avvio analisi...")

        def worker():
            try:
                analysis = PIRAnalysis(inp, out, logger=self.write_log)
                analysis.run_all()
                self.write_log(f"\nOutput salvato in: {Path(out).resolve()}")
                messagebox.showinfo(APP_TITLE, f"Analisi completata.\nOutput: {Path(out).resolve()}")
            except Exception:
                self.write_log("\nERRORE:\n" + traceback.format_exc())
                messagebox.showerror(APP_TITLE, "Errore durante l'analisi. Guarda il log.")
            finally:
                self.running = False
                self.progress.stop()
                self.run_btn.config(state="normal")

        Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
