import json
import sys
from pathlib import Path
from typing import Literal, cast

import httpx
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from carbonlens.config import Settings
from carbonlens.data.export import report_csv

st.set_page_config(page_title="CarbonLens", page_icon=":material/eco:", layout="wide")
st.title("CarbonLens", anchor=False)
st.caption("CLOUD USAGE / EMISSIONS ESTIMATES / HUMAN REVIEW")

config = Settings()
for name, default in {"report": None, "onboarding_recorded": False}.items():
    if name not in st.session_state:
        st.session_state[name] = default


def request_api(method, path, **kwargs):
    try:
        with httpx.Client(
            base_url=config.api_url.rstrip("/"),
            timeout=45,
            headers={"X-API-Key": config.api_key} if config.api_key else {},
        ) as client:
            response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        try:
            detail = error.response.json().get("detail", "Request failed.")
        except ValueError:
            detail = "The API returned an unexpected response."
        if isinstance(detail, dict) and "errors" in detail:
            for message in detail["errors"]:
                st.error(message)
        elif isinstance(detail, list):
            st.error("Invalid request parameters. Check the input values.")
        else:
            st.error(str(detail))
    except (httpx.RequestError, ValueError):
        st.error("CarbonLens API is unavailable. Check that the backend is running.")
    return None


with st.sidebar:
    st.header("Workspace", anchor=False)
    capabilities = request_api("GET", "/api/v1/config")
    if capabilities:
        st.badge("API connected", icon=":material/check_circle:", color="green")
        if not st.session_state.onboarding_recorded:
            request_api("POST", "/api/v1/events", json={"name": "onboarding_started"})
            st.session_state.onboarding_recorded = True
    else:
        st.badge("API offline", icon=":material/cloud_off:", color="red")
    with st.form("analysis_parameters"):
        upload_format = st.selectbox(
            "CSV format",
            [
                "CarbonLens template",
                "AWS CUR",
                "Azure Cost Management",
                "GCP Billing export",
            ],
        )
        uploaded = st.file_uploader(
            "Cloud usage CSV", type=["csv"], max_upload_size=config.max_upload_mb
        )
        top_n = st.number_input("Maximum recommendations", min_value=1, max_value=3, value=3)
        use_ai = st.toggle(
            "AI-assisted action labels",
            value=False,
            disabled=not bool(capabilities and capabilities["ai_available"]),
        )
        analyze = st.form_submit_button(
            "Analyze upload",
            icon=":material/analytics:",
            type="primary",
            width="stretch",
            disabled=not capabilities,
        )
    if analyze:
        if uploaded is None:
            st.error("Choose a CSV file first.")
        else:
            export_providers = {
                "AWS CUR": "aws",
                "Azure Cost Management": "azure",
                "GCP Billing export": "gcp",
            }
            provider = export_providers.get(upload_format)
            endpoint = "/api/v1/analyses/exports" if provider else "/api/v1/analyses"
            parameters: dict[str, int | bool | str] = {"top_n": top_n, "use_ai": use_ai}
            if provider:
                parameters["provider"] = provider
            with st.spinner("Validating and analyzing usage export..."):
                report = request_api(
                    "POST",
                    endpoint,
                    params=parameters,
                    files={"file": (uploaded.name, uploaded.getvalue(), "text/csv")},
                )
            if report:
                st.session_state.report = report
    sample_dataset = st.segmented_control(
        "Sample dataset",
        ["Mixed usage", "AWS electricity (2023)"],
        default="Mixed usage",
        key="sample_dataset",
    )
    sample_profile = "mixed" if sample_dataset == "Mixed usage" else "aws-electricity-2023"
    if st.button(
        "Analyze sample", icon=":material/science:", width="stretch", disabled=not capabilities
    ):
        with st.spinner("Analyzing synthetic sample..."):
            report = request_api(
                "POST",
                "/api/v1/analyses/sample",
                params={"top_n": top_n, "use_ai": use_ai, "profile": sample_profile},
            )
        if report:
            st.session_state.report = report
    st.divider()
    st.subheader("Saved reports", anchor=False)
    history = request_api("GET", "/api/v1/analyses") if capabilities else []
    if history:
        report_ids = [item["id"] for item in history]
        labels = {
            item[
                "id"
            ]: f"{item['created_at'][:16].replace('T', ' ')} UTC / {item['summary']['total_rows']} rows"
            for item in history
        }
        selected = st.selectbox("Report", report_ids, format_func=lambda value: labels[value])
        if st.button("Open report", icon=":material/folder_open:", width="stretch"):
            saved = request_api("GET", f"/api/v1/analyses/{selected}")
            if saved:
                st.session_state.report = saved
    else:
        st.caption("No saved reports")
    st.divider()
    st.link_button(
        "API reference",
        f"{config.public_api_url.rstrip('/')}/docs",
        icon=":material/api:",
        width="stretch",
    )
    st.caption("Experimental prototype. No cloud resources are modified.")

report = st.session_state.report
if report is None:
    st.subheader("Usage workspace", anchor=False)
    sample_filename = (
        "sample_cloud_usage.csv" if sample_profile == "mixed" else "sample_aws_electricity_2023.csv"
    )
    sample_path = Path(__file__).parent / "data" / sample_filename
    sample = pd.read_csv(sample_path)
    with st.container(horizontal=True):
        st.metric("Supported providers", "3")
        st.metric(
            "Configured factors",
            str(capabilities["configured_factors"]) if capabilities else "Unavailable",
        )
        st.metric("Automatic cloud changes", "Disabled")
    st.subheader("Synthetic sample", anchor=False)
    st.dataframe(sample, hide_index=True, alt="Synthetic usage for the selected sample dataset")
    with st.container(horizontal=True):
        st.download_button(
            "Sample CSV",
            sample_path.read_bytes(),
            sample_filename,
            "text/csv",
            icon=":material/download:",
        )
        st.download_button(
            "CSV template",
            sample.iloc[:0].to_csv(index=False),
            "cloud_usage_template.csv",
            "text/csv",
            icon=":material/table_view:",
        )
    st.warning(
        "Operational screening only. Compute and storage ranges use cited CCF assumptions and annual grid proxies; GPUs, network, embodied emissions and storage replication are excluded."
    )
    with st.expander("Input contract"):
        st.table(
            pd.DataFrame(
                {
                    "Required fields": [
                        "provider",
                        "service / region",
                        "usage_quantity / usage_unit",
                        "period_start / period_end",
                        "cost_amount / currency",
                        "energy_basis / energy_source",
                        "data_basis / provider fields",
                    ],
                    "Accepted values": [
                        "aws, azure, gcp",
                        "Nonempty; must match a configured factor for estimation",
                        "Finite nonnegative quantity; compatible input unit",
                        "YYYY-MM-DD; end on or after start",
                        "Optional cost; uppercase three-letter currency required with cost",
                        "For the reference: facility / nonempty evidence reference; energy includes cooling overhead",
                        "usage_only (default), or provider_reported with provider_kg_co2e, provider_methodology, provider_source_url and provider_access_date",
                    ],
                }
            ),
            alt="Required CSV columns and accepted values",
        )
    st.stop()

if st.session_state.get("viewed_report") != report["id"]:
    request_api("POST", "/api/v1/events", json={"name": "report_viewed", "report_id": report["id"]})
    st.session_state.viewed_report = report["id"]

if report.get("methodology_version") != "2":
    st.warning(
        "This saved report predates ranged estimates. Reanalyze the original CSV for methodology v2."
    )
    st.stop()

st.subheader("Analysis report", anchor=False)
st.caption(f"{report['created_at'][:19].replace('T', ' ')} UTC | {report['id']}")
summary = report["summary"]
with st.container(horizontal=True):
    total = summary["estimated_kg_co2e"]
    st.metric("Central kg CO2e", f"{total:,.4g}" if total is not None else "See method groups")
    st.metric("Estimation coverage", f"{summary['coverage_percent']:g}%")
    st.metric("Usage rows", str(summary["total_rows"]))
    st.metric(
        "Awaiting review",
        str(sum(item["decision"] == "pending" for item in report["recommendations"])),
    )
if total is not None:
    st.text(
        f"Method: {summary['method']} | Scenario range: {summary['low_kg_co2e']:.6g} to {summary['high_kg_co2e']:.6g} kg CO2e"
    )
    st.caption(summary["range_assumption"])
if summary.get("totals_by_method"):
    st.dataframe(
        pd.DataFrame(summary["totals_by_method"]),
        hide_index=True,
        alt="Totals separated by estimate method and accounting basis, with low central high scenarios and input-row references",
    )
for message in report["warnings"]:
    st.warning(message)
if summary["not_estimated_rows"]:
    st.warning(
        f"{summary['not_estimated_rows']} of {summary['total_rows']} rows could not be estimated. Report totals exclude those rows."
    )

view = st.segmented_control(
    "Report view",
    ["Overview", "Usage & provenance", "Recommendations", "Methodology"],
    default="Overview",
    key="report_view",
)
frame = pd.DataFrame(report["rows"])

if view == "Overview":
    st.subheader("Estimation coverage by provider", anchor=False)
    coverage = frame.groupby(["provider", "status"]).size().rename("Usage rows").reset_index()
    st.bar_chart(
        coverage,
        x="provider",
        y="Usage rows",
        color="status",
        horizontal=True,
        alt="Estimated and unestimated usage rows by cloud provider",
    )
    estimated = frame[frame["status"] == "estimated"]
    if not estimated.empty:
        st.subheader("Emissions by input row", anchor=False)
        st.dataframe(
            estimated[
                [
                    "row_id",
                    "provider",
                    "service",
                    "method",
                    "accounting_method",
                    "low_kg_co2e",
                    "central_kg_co2e",
                    "high_kg_co2e",
                    "range_assumption",
                ]
            ],
            hide_index=True,
            alt="Per-row emissions methods and low central high scenario values; no incompatible scopes are combined",
        )
    if summary["costs_by_currency"]:
        st.subheader("Reported cost", anchor=False)
        with st.container(horizontal=True):
            for currency, amount in summary["costs_by_currency"].items():
                st.metric(currency, f"{amount:,.2f}")
    st.caption("Cost is reported separately and is not used as an emissions proxy.")
    st.subheader("Agent workflow", anchor=False)
    st.dataframe(
        pd.DataFrame(
            {
                "Stage": [
                    "Validate CSV",
                    "Calculate supported rows",
                    "Rank supported hotspots",
                    "Human review",
                ],
                "Status": [
                    "Complete",
                    "Complete",
                    "Complete",
                    "Pending"
                    if any(item["decision"] == "pending" for item in report["recommendations"])
                    else "No pending decisions",
                ],
            }
        ),
        hide_index=True,
        alt="Completed agent stages and human review status",
    )

elif view == "Usage & provenance":
    with st.container(horizontal=True):
        providers = st.multiselect("Provider", sorted(frame["provider"].unique()))
        statuses = st.multiselect("Estimation status", ["estimated", "not_estimated"])
        regions = st.multiselect("Region", sorted(frame["region"].unique()))
    filtered = frame.copy()
    for column, values in (("provider", providers), ("status", statuses), ("region", regions)):
        if values:
            filtered = filtered[filtered[column].isin(values)]
    st.dataframe(
        filtered.drop(columns=["factor", "provenance", "assumptions"]),
        hide_index=True,
        alt="Filtered usage rows with estimate status, reasons, and factor IDs",
    )
    for row in filtered.to_dict(orient="records"):
        with st.expander(f"Row {row['row_id']} / {row['method']}"):
            st.json(
                {
                    "formula": row["formula"],
                    "provenance": row["provenance"],
                    "assumptions": row["assumptions"],
                    "range_assumption": row["range_assumption"],
                    "reason": row["reason"],
                }
            )

elif view == "Recommendations":
    st.caption("Approval records a decision only. No infrastructure change or savings is implied.")
    if not report["recommendations"]:
        st.info("No supported estimated hotspots are available for recommendations.")
    for item in report["recommendations"]:
        with st.container(border=True):
            st.subheader(item["title"], anchor=False)
            st.text(item["explanation"])
            st.text(f"Method: {item['method']} | Range assumption: {item['range_assumption']}")
            st.badge(
                item["decision"].capitalize(),
                color=cast(
                    Literal["orange", "green", "red"],
                    {"pending": "orange", "approved": "green", "rejected": "red"}[item["decision"]],
                ),
            )
            if item.get("evidence"):
                st.markdown("**Evidence**")
                for evidence in item["evidence"]:
                    st.text(evidence)
            if item.get("effort"):
                st.text(f"Effort: {item['effort']}")
            if item.get("risks"):
                st.markdown("**Operational risks**")
                for risk in item["risks"]:
                    st.text(risk)
            if item.get("next_steps"):
                with st.expander("Next steps"):
                    for index, step in enumerate(item["next_steps"], start=1):
                        st.text(f"{index}. {step}")
            if item.get("savings_reason"):
                st.caption(f"Potential savings: not estimated. {item['savings_reason']}")
            if item.get("ai_action"):
                st.text(f"AI candidate: {item['ai_action'].replace('_', ' ')}")
            with st.container(horizontal=True):
                for decision, icon in (
                    ("approved", ":material/check:"),
                    ("rejected", ":material/close:"),
                ):
                    if st.button(
                        "Approve" if decision == "approved" else "Reject",
                        icon=icon,
                        key=f"{report['id']}_{item['id']}_{decision}",
                        disabled=item["decision"] == decision,
                    ):
                        updated = request_api(
                            "POST",
                            f"/api/v1/analyses/{report['id']}/decisions",
                            json={"recommendation_id": item["id"], "decision": decision},
                        )
                        if updated:
                            st.session_state.report = updated
                            st.rerun()

elif view == "Methodology":
    for limitation in report["limitations"]:
        st.text(limitation)
    st.text(f"Explanation mode: {report['explanation_mode']}")
    registry = request_api("GET", "/api/v1/registry")
    factors = registry["factors"] if registry else []
    if registry:
        st.caption(f"Methodology v2 | Registry {registry['registry_version']}")
        with st.expander("Usage coefficients and source assumptions"):
            st.json(registry["usage_profiles"])
    if factors:
        st.dataframe(
            pd.DataFrame(factors),
            hide_index=True,
            alt="Configured emission factors and their sources and validity dates",
        )
    else:
        st.info(
            "No factors are configured. Supply a reviewed factor file on the API server to enable supported estimates."
        )

st.divider()
with st.container(horizontal=True):
    st.download_button(
        "Report JSON",
        json.dumps(report, indent=2),
        f"carbonlens-{report['id']}.json",
        "application/json",
        icon=":material/download:",
    )
    st.download_button(
        "Results CSV",
        report_csv(report),
        f"carbonlens-{report['id']}.csv",
        "text/csv",
        icon=":material/table_view:",
    )
