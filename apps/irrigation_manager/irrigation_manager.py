"""ET0-based irrigation manager for Home Assistant and AppDaemon.

Initial AppDaemon migration of the Home Assistant automation
"Arrosage - Gazon intelligent ET0 + WAGO - MONOBLOC".

This first version deliberately keeps the existing Home Assistant helpers and
WAGO entities. The objective is behavioural compatibility first; helpers can
be reduced later without changing the hydric calculation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

import appdaemon.plugins.hass.hassapi as hass


DEFAULT_ENTITIES: dict[str, str] = {
    # Modes and lifecycle
    "initialized": "input_boolean.arrosage_gazon_v2_initialise",
    "mode_auto": "input_boolean.arrosage_gazon_mode_auto",
    "restriction_toggle": "input_boolean.arrosage_gazon_restriction_eau",
    "restriction_configured": "input_boolean.arrosage_gazon_horaire_restriction_configure",
    "cycle_in_progress": "input_boolean.arrosage_gazon_cycle_en_cours",
    "wago_seen": "input_boolean.arrosage_gazon_wago_a_ete_actif",
    "cycle_abandoned": "input_boolean.arrosage_gazon_cycle_abandonne",

    # User commands
    "test_calculation": "input_button.arrosage_gazon_test_calcul",
    "manual_start": "input_button.arrosage_gazon_lancer_arrosage",
    "wet_soil_recalibration": "input_button.arrosage_gazon_recalage_sol_humide",

    # Parameters and hydric state
    "kc": "input_number.arrosage_gazon_kc",
    "threshold_normal": "input_number.arrosage_gazon_seuil_declenchement_mm",
    "threshold_heatwave": "input_number.arrosage_gazon_seuil_canicule_mm",
    "target_after_irrigation": "input_number.arrosage_gazon_cible_apres_arrosage_mm",
    "deficit_max": "input_number.arrosage_gazon_deficit_max_mm",
    "application_max": "input_number.arrosage_gazon_apport_max_mm",
    "mm_per_multiplier": "input_number.arrosage_gazon_mm_par_multiplicateur",
    "multiplier_max": "input_number.arrosage_gazon_multiplicateur_max",
    "rain_block_mm": "input_number.arrosage_gazon_pluie_blocage_mm",
    "rain_probability_block_pct": "input_number.arrosage_gazon_probabilite_pluie_report_pct",
    "deficit_emergency": "input_number.arrosage_gazon_deficit_urgence_mm",
    "rain_efficiency": "input_number.arrosage_gazon_pluie_efficacite",
    "rain_initial_loss": "input_number.arrosage_gazon_pluie_perte_initiale_mm",
    "offset_normal_min": "input_number.arrosage_gazon_decalage_normal_min",
    "offset_restriction_min": "input_number.arrosage_gazon_decalage_restriction_min",
    "deficit": "input_number.arrosage_gazon_deficit_mm",
    "irrigation_credit": "input_number.arrosage_gazon_credit_arrosage_mm",

    # Forecast outputs
    "forecast_deficit": "input_number.arrosage_gazon_prevision_deficit_mm",
    "forecast_deficit_after": "input_number.arrosage_gazon_prevision_deficit_apres_mm",
    "forecast_etc": "input_number.arrosage_gazon_prevision_etc_mm",
    "forecast_effective_rain": "input_number.arrosage_gazon_prevision_pluie_efficace_mm",
    "forecast_threshold": "input_number.arrosage_gazon_prevision_seuil_mm",
    "forecast_water": "input_number.arrosage_gazon_prevision_eau_mm",
    "forecast_cycles": "input_number.arrosage_gazon_prevision_cycles",
    "forecast_multiplier": "input_number.arrosage_gazon_prevision_multiplicateur",
    "forecast_rain_tomorrow": "input_number.arrosage_gazon_prevision_pluie_demain_mm",
    "forecast_rain_probability_tomorrow": "input_number.arrosage_gazon_prevision_proba_pluie_demain_pct",

    # Snapshot of a launched cycle
    "cycle_deficit_before": "input_number.arrosage_gazon_cycle_deficit_avant_mm",
    "cycle_deficit_after": "input_number.arrosage_gazon_cycle_deficit_apres_mm",
    "cycle_water_planned": "input_number.arrosage_gazon_cycle_eau_prevue_mm",
    "cycle_cycles_started": "input_number.arrosage_gazon_cycle_cycles_lances",
    "cycle_multiplier_started": "input_number.arrosage_gazon_cycle_multiplicateur_lance",

    # Weather
    "weather_ok": "binary_sensor.arrosage_gazon_v31_meteo_open_meteo_ok",
    "temperature_7d": "sensor.temperature_exterieure_moyenne_7j",
    "temperature_now": "sensor.temperature_exterieur_moyenne",
    "wind_24h": "sensor.vitesse_vent_moyenne_24h",
    "et0_today": "sensor.arrosage_gazon_v31_et0_aujourdhui",
    "rain_today": "sensor.arrosage_gazon_v31_pluie_aujourdhui",
    "rain_tomorrow": "sensor.arrosage_gazon_v31_pluie_demain",
    "rain_probability_tomorrow": "sensor.arrosage_gazon_v31_probabilite_pluie_demain",
    "temperature_max_today": "sensor.arrosage_gazon_v31_temperature_max_aujourdhui",
    "et0_yesterday": "sensor.arrosage_gazon_v31_et0_hier",
    "rain_yesterday": "sensor.arrosage_gazon_v31_pluie_hier",

    # Restriction and WAGO
    "restriction_active": "binary_sensor.arrosage_gazon_restriction_eau_active",
    "restriction_entity_id": "input_text.arrosage_gazon_restriction_entity_id",
    "wago_active": "binary_sensor.arrosage_gazon_wago_actif",
    "wago_cycles": "number.wago_sps_arrosage_gazon_cycles",
    "wago_multiplier": "number.wago_sps_arrosage_gazon_multiplicateur",
    "wago_start": "button.wago_sps_arrosage_gazon_start",
    "wago_stop": "button.wago_sps_arrosage_gazon_stop",

    # Datetimes and status text
    "next_departure": "input_datetime.arrosage_gazon_prochain_depart_auto",
    "sunset_reference": "input_datetime.arrosage_gazon_coucher_reference",
    "last_balance": "input_datetime.arrosage_gazon_dernier_bilan",
    "cycle_start": "input_datetime.arrosage_gazon_cycle_debut",
    "last_hydric_day": "input_text.arrosage_gazon_dernier_jour_hydrique",
    "planned_day": "input_text.arrosage_gazon_jour_planifie",
    "status": "input_text.arrosage_gazon_etat",
    "schedule_status": "input_text.arrosage_gazon_horaire_etat",
    "weather_source": "input_text.arrosage_gazon_source_meteo",
    "sun": "sun.sun",
}


DEFAULTS: dict[str, float] = {
    "kc": 0.8,
    "threshold_normal": 8.0,
    "threshold_heatwave": 6.0,
    "target_after_irrigation": 2.0,
    "deficit_max": 35.0,
    "application_max": 15.0,
    "mm_per_multiplier": 5.0,
    "multiplier_max": 3.0,
    "rain_block_mm": 5.0,
    "rain_probability_block_pct": 60.0,
    "deficit_emergency": 14.0,
    "rain_efficiency": 0.85,
    "rain_initial_loss": 1.0,
    "offset_normal_min": 90.0,
    "offset_restriction_min": 0.0,
    "deficit": 2.0,
    "irrigation_credit": 0.0,
}


@dataclass(frozen=True)
class Plan:
    weather_ok: bool
    etc_today: float
    effective_rain_today: float
    projected_deficit: float
    heatwave: bool
    effective_threshold: float
    postpone_for_rain: bool
    water_requested: float
    total_multiplier: float
    cycles: int
    wago_multiplier: float
    estimated_water: float
    projected_deficit_after: float
    rain_tomorrow: float
    rain_probability_tomorrow: float


class IrrigationManager(hass.Hass):
    """ET0 hydric balance, scheduling and WAGO cycle management."""

    def initialize(self) -> None:
        self.entities = dict(DEFAULT_ENTITIES)
        self.entities.update(self.args.get("entities", {}))
        self._departure_handle = None

        self._initialize_defaults_if_needed()

        now = self.datetime()
        first = now.replace(second=0, microsecond=0)
        minute_mod = first.minute % 5
        if minute_mod:
            first += timedelta(minutes=5 - minute_mod)
        elif first <= now:
            first += timedelta(minutes=5)

        self.run_every(self._surveillance, first, 5 * 60)
        self.run_daily(self._daily_balance_trigger, time(12, 10))
        self.run_at_sunset(self._sunset_trigger)

        self.listen_state(self._test_calculation, self.e("test_calculation"))
        self.listen_state(self._manual_start, self.e("manual_start"))
        self.listen_state(self._wet_soil_recalibration, self.e("wet_soil_recalibration"))

        self.listen_state(self._wago_changed, self.e("wago_active"))
        self.listen_state(
            self._wago_off_confirmed,
            self.e("wago_active"),
            new="off",
            duration=20 * 60,
        )
        self.listen_state(self._wago_stop_pressed, self.e("wago_stop"))

        for key in (
            "offset_normal_min",
            "offset_restriction_min",
            "restriction_toggle",
            "restriction_configured",
            "restriction_entity_id",
            "restriction_active",
        ):
            self.listen_state(self._schedule_input_changed, self.e(key))

        self._refresh_forecast()
        self._maybe_daily_balance("startup")
        self._restore_departure_after_restart()
        self.log("Irrigation Manager initialized")

    # ------------------------------------------------------------------
    # HA helpers
    # ------------------------------------------------------------------

    def e(self, key: str) -> str:
        return self.entities[key]

    def state(self, key: str, default: Any = None) -> Any:
        value = self.get_state(self.e(key))
        if value in (None, "unknown", "unavailable"):
            return default
        return value

    def number(self, key: str, default: float | None = None) -> float:
        if default is None:
            default = DEFAULTS.get(key, 0.0)
        try:
            return float(self.state(key, default))
        except (TypeError, ValueError):
            return float(default)

    def is_on(self, key: str) -> bool:
        return self.get_state(self.e(key)) == "on"

    def _set_number(self, key: str, value: float | int) -> None:
        self.call_service("input_number/set_value", entity_id=self.e(key), value=value)

    def _set_text(self, key: str, value: str) -> None:
        self.call_service("input_text/set_value", entity_id=self.e(key), value=value)

    def _set_datetime(self, key: str, value: datetime | None = None) -> None:
        value = value or self.datetime()
        self.call_service(
            "input_datetime/set_datetime",
            entity_id=self.e(key),
            datetime=value.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _turn_on(self, key: str) -> None:
        self.turn_on(self.e(key))

    def _turn_off(self, key: str) -> None:
        self.turn_off(self.e(key))

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _initialize_defaults_if_needed(self) -> None:
        if self.is_on("initialized") or self.is_on("wago_active"):
            return

        for key, value in DEFAULTS.items():
            self._set_number(key, value)

        for key in (
            "restriction_configured",
            "cycle_in_progress",
            "wago_seen",
            "cycle_abandoned",
        ):
            self._turn_off(key)

        self._turn_on("initialized")
        self._set_text(
            "status",
            "Moteur ET0 AppDaemon initialisé · déficit de départ 2 mm · horaire normal +90 min.",
        )

    # ------------------------------------------------------------------
    # Hydric calculation
    # ------------------------------------------------------------------

    def _fallback_etc(self) -> float:
        t7 = self.number("temperature_7d", 0.0)
        t_now = self.number("temperature_now", 0.0)
        wind = self.number("wind_24h", 0.0)

        if t7 < 12:
            base = 0.5
        elif t7 < 15:
            base = 1.0
        elif t7 < 20:
            base = 2.0
        elif t7 < 25:
            base = 3.0
        elif t7 < 28:
            base = 4.0
        else:
            base = 5.0

        heat = 1.0 if t_now >= 35 else 0.7 if t_now >= 32 else 0.4 if t_now >= 30 else 0.0
        wind_bonus = 1.0 if wind >= 35 else 0.6 if wind >= 25 else 0.3 if wind >= 15 else 0.0
        return round(max(0.0, min(base + heat + wind_bonus, 7.5)), 1)

    def _build_plan(self, ignore_future_rain: bool = False) -> Plan:
        weather_ok = self.is_on("weather_ok")
        kc = self.number("kc", 0.8)
        deficit_memory = self.number("deficit", 0.0)
        irrigation_credit = self.number("irrigation_credit", 0.0)
        deficit_max = self.number("deficit_max", 35.0)

        et0_today = self.number("et0_today", 0.0)
        rain_today = self.number("rain_today", 0.0)
        rain_tomorrow = self.number("rain_tomorrow", 0.0)
        rain_probability = self.number("rain_probability_tomorrow", 0.0)
        tmax_today = self.number(
            "temperature_max_today",
            self.number("temperature_now", 0.0),
        )

        if weather_ok and et0_today >= 0:
            etc_today = round(et0_today * kc, 1)
        else:
            etc_today = self._fallback_etc()

        if weather_ok:
            effective_rain_today = round(
                max(rain_today - self.number("rain_initial_loss", 1.0), 0.0)
                * self.number("rain_efficiency", 0.85),
                1,
            )
        else:
            effective_rain_today = 0.0

        projected_deficit = round(
            max(
                0.0,
                min(
                    deficit_memory + etc_today - effective_rain_today - irrigation_credit,
                    deficit_max,
                ),
            ),
            1,
        )

        heatwave = tmax_today >= 30
        effective_threshold = (
            self.number("threshold_heatwave", 6.0)
            if heatwave
            else self.number("threshold_normal", 8.0)
        )

        postpone_for_rain = (
            not ignore_future_rain
            and weather_ok
            and rain_tomorrow >= self.number("rain_block_mm", 5.0)
            and rain_probability >= self.number("rain_probability_block_pct", 60.0)
            and projected_deficit < self.number("deficit_emergency", 14.0)
        )

        needs_irrigation = projected_deficit >= effective_threshold
        if needs_irrigation and not postpone_for_rain:
            water_requested = round(
                min(
                    max(
                        projected_deficit - self.number("target_after_irrigation", 2.0),
                        0.0,
                    ),
                    self.number("application_max", 15.0),
                ),
                1,
            )
        else:
            water_requested = 0.0

        mm_per_multiplier = self.number("mm_per_multiplier", 5.0)
        if mm_per_multiplier > 0:
            total_multiplier = round(
                max(
                    0.0,
                    min(
                        water_requested / mm_per_multiplier,
                        self.number("multiplier_max", 3.0),
                    ),
                ),
                2,
            )
        else:
            total_multiplier = 0.0

        cycles = (
            max(1, min(math.ceil(total_multiplier / 0.5), 6))
            if total_multiplier > 0
            else 0
        )
        wago_multiplier = round(total_multiplier / cycles, 1) if cycles else 0.0
        estimated_water = round(cycles * wago_multiplier * mm_per_multiplier, 1)
        projected_deficit_after = round(max(projected_deficit - estimated_water, 0.0), 1)

        return Plan(
            weather_ok=weather_ok,
            etc_today=etc_today,
            effective_rain_today=effective_rain_today,
            projected_deficit=projected_deficit,
            heatwave=heatwave,
            effective_threshold=effective_threshold,
            postpone_for_rain=postpone_for_rain,
            water_requested=water_requested,
            total_multiplier=total_multiplier,
            cycles=cycles,
            wago_multiplier=wago_multiplier,
            estimated_water=estimated_water,
            projected_deficit_after=projected_deficit_after,
            rain_tomorrow=rain_tomorrow,
            rain_probability_tomorrow=rain_probability,
        )

    def _refresh_forecast(self) -> Plan:
        plan = self._build_plan()
        values = {
            "forecast_deficit": plan.projected_deficit,
            "forecast_deficit_after": plan.projected_deficit_after,
            "forecast_etc": plan.etc_today,
            "forecast_effective_rain": plan.effective_rain_today,
            "forecast_threshold": plan.effective_threshold,
            "forecast_water": plan.estimated_water,
            "forecast_cycles": plan.cycles,
            "forecast_multiplier": plan.wago_multiplier,
            "forecast_rain_tomorrow": plan.rain_tomorrow,
            "forecast_rain_probability_tomorrow": plan.rain_probability_tomorrow,
        }
        for key, value in values.items():
            self._set_number(key, value)

        self._set_text(
            "weather_source",
            "Open-Meteo ET0 FAO-56"
            if plan.weather_ok
            else "Repli température/vent (Open-Meteo indisponible)",
        )
        return plan

    # ------------------------------------------------------------------
    # Daily hydric balance
    # ------------------------------------------------------------------

    def _daily_balance_trigger(self, kwargs: dict[str, Any]) -> None:
        self._maybe_daily_balance("12:10")

    def _maybe_daily_balance(self, source: str) -> None:
        if self.is_on("cycle_in_progress"):
            return

        yesterday = (self.datetime() - timedelta(days=1)).strftime("%Y-%m-%d")
        if self.state("last_hydric_day", "") == yesterday:
            return

        now = self.datetime()
        if now.hour < 12:
            return

        weather_ok = self.is_on("weather_ok")
        if not weather_ok and now.hour < 18:
            return

        et0_yesterday = self.number("et0_yesterday", 0.0)
        rain_yesterday = self.number("rain_yesterday", 0.0)
        kc = self.number("kc", 0.8)

        etc_yesterday = (
            round(et0_yesterday * kc, 1)
            if weather_ok
            else self._fallback_etc()
        )

        if weather_ok:
            effective_rain_yesterday = round(
                max(rain_yesterday - self.number("rain_initial_loss", 1.0), 0.0)
                * self.number("rain_efficiency", 0.85),
                1,
            )
        else:
            effective_rain_yesterday = 0.0

        deficit_before = self.number("deficit", 0.0)
        credit = self.number("irrigation_credit", 0.0)
        deficit_after = round(
            max(
                0.0,
                min(
                    deficit_before + etc_yesterday - effective_rain_yesterday - credit,
                    self.number("deficit_max", 35.0),
                ),
            ),
            1,
        )

        self._set_number("deficit", deficit_after)
        self._set_number("irrigation_credit", 0)
        self._set_text("last_hydric_day", yesterday)
        self._set_datetime("last_balance")
        self._set_text(
            "status",
            f"Bilan {yesterday} · déficit {deficit_before:.1f} + ETc {etc_yesterday:.1f} "
            f"- pluie eff. {effective_rain_yesterday:.1f} - eau confirmée {credit:.1f} "
            f"= {deficit_after:.1f} mm · {'Open-Meteo' if weather_ok else 'repli météo'}.",
        )
        self.log(f"Daily hydric balance applied ({source}): {deficit_after:.1f} mm")

    # ------------------------------------------------------------------
    # Night scheduling and restriction handling
    # ------------------------------------------------------------------

    def _sunset_trigger(self, kwargs: dict[str, Any]) -> None:
        now = self.datetime()
        self._set_datetime("sunset_reference", now)
        self._set_text("planned_day", now.strftime("%Y-%m-%d"))
        self._schedule_from_reference(now, "sunset")

        plan = self._refresh_forecast()
        rain_note = (
            f" · REPORT pluie demain {plan.rain_tomorrow:.1f} mm / "
            f"{plan.rain_probability_tomorrow:.0f} %"
            if plan.postpone_for_rain
            else ""
        )
        self._set_text(
            "status",
            f"Plan nuit · déficit prévu {plan.projected_deficit:.1f} mm · "
            f"ETc {plan.etc_today:.1f} · pluie eff. {plan.effective_rain_today:.1f} · "
            f"{plan.cycles} x {plan.wago_multiplier:.1f} · eau {plan.estimated_water:.1f} mm"
            f"{rain_note}.",
        )

    def _schedule_input_changed(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if old == new or self.get_state(self.e("sun")) != "below_horizon":
            return

        reference = self._parse_datetime(self.state("sunset_reference"))
        if reference is None:
            return

        age = (self.datetime() - reference).total_seconds()
        if 0 <= age < 57600:
            self._schedule_from_reference(reference, "configuration changed")

    def _schedule_from_reference(self, reference: datetime, reason: str) -> None:
        restriction_active = self.is_on("restriction_active")
        restriction_configured = self.is_on("restriction_configured")
        offset = (
            self.number("offset_restriction_min", 0.0)
            if restriction_active
            else self.number("offset_normal_min", 90.0)
        )
        desired = reference + timedelta(minutes=offset)
        self._set_datetime("next_departure", desired)

        if restriction_active and not restriction_configured:
            self._cancel_departure()
            self._set_text(
                "schedule_status",
                "Restriction active · départ auto BLOQUÉ jusqu'à validation du créneau autorisé.",
            )
            self.log(f"Automatic departure blocked by restriction ({reason})")
            return

        self._set_text(
            "schedule_status",
            (
                f"Restriction active · créneau validé · départ {desired.strftime('%H:%M')}."
                if restriction_active
                else f"Horaire normal · départ {desired.strftime('%H:%M')}."
            ),
        )

        seconds = (desired - self.datetime()).total_seconds()
        if seconds < -60:
            self.log(f"Target departure already passed: {desired}", level="DEBUG")
            return

        self._cancel_departure()
        self._departure_handle = self.run_in(self._automatic_departure, max(0, seconds))
        self.log(f"Automatic irrigation scheduled for {desired} ({reason})")

    def _restore_departure_after_restart(self) -> None:
        desired = self._parse_datetime(self.state("next_departure"))
        if desired is None:
            return

        seconds = (desired - self.datetime()).total_seconds()
        if not 0 < seconds < 16 * 3600:
            return

        if self.is_on("restriction_active") and not self.is_on("restriction_configured"):
            return

        self._cancel_departure()
        self._departure_handle = self.run_in(self._automatic_departure, seconds)
        self.log(f"Restored automatic departure after restart: {desired}")

    def _cancel_departure(self) -> None:
        if self._departure_handle is None:
            return
        try:
            self.cancel_timer(self._departure_handle)
        except Exception:  # AppDaemon may already have consumed the handle.
            pass
        self._departure_handle = None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or value in ("unknown", "unavailable", "none"):
            return None
        text = str(value)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Automatic/manual launch and WAGO confirmation
    # ------------------------------------------------------------------

    def _automatic_departure(self, kwargs: dict[str, Any]) -> None:
        self._departure_handle = None
        plan = self._build_plan()

        restriction_allowed = (
            not self.is_on("restriction_active")
            or self.is_on("restriction_configured")
        )
        auto_ok = (
            self.is_on("mode_auto")
            and restriction_allowed
            and not self.is_on("cycle_in_progress")
            and plan.cycles > 0
            and plan.wago_multiplier > 0
            and plan.estimated_water > 0
        )

        if auto_ok:
            self._launch_cycle(plan, "AUTO")
            return

        if not self.is_on("mode_auto"):
            reason = "mode auto OFF"
        elif self.is_on("restriction_active") and not self.is_on("restriction_configured"):
            reason = "restriction active sans créneau autorisé validé"
        elif plan.estimated_water <= 0:
            reason = "aucun arrosage prévu / report pluie"
        elif self.is_on("cycle_in_progress"):
            reason = "cycle déjà en cours"
        else:
            reason = "plan invalide"
        self._set_text("status", f"Départ auto non exécuté · {reason}.")

    def _manual_start(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if old == new:
            return

        # The original manual command ignores future-rain postponement but
        # still requires the hydric deficit threshold to be reached.
        plan = self._build_plan(ignore_future_rain=True)
        if (
            not self.is_on("cycle_in_progress")
            and plan.cycles > 0
            and plan.wago_multiplier > 0
        ):
            self._launch_cycle(plan, "MANUEL")
            return

        self._set_text(
            "status",
            f"Lancement manuel hydrique refusé · déficit prévu {plan.projected_deficit:.1f} mm "
            f"/ seuil {plan.effective_threshold:.1f} mm ou cycle déjà en cours.",
        )

    def _launch_cycle(self, plan: Plan, mode: str) -> None:
        self.call_service("number/set_value", entity_id=self.e("wago_cycles"), value=plan.cycles)
        self.call_service(
            "number/set_value",
            entity_id=self.e("wago_multiplier"),
            value=plan.wago_multiplier,
        )

        for key, value in {
            "cycle_deficit_before": plan.projected_deficit,
            "cycle_deficit_after": plan.projected_deficit_after,
            "cycle_water_planned": plan.estimated_water,
            "cycle_cycles_started": plan.cycles,
            "cycle_multiplier_started": plan.wago_multiplier,
        }.items():
            self._set_number(key, value)

        self._turn_off("wago_seen")
        self._turn_off("cycle_abandoned")
        self._turn_on("cycle_in_progress")
        self._set_datetime("cycle_start")
        self.run_in(self._press_wago_start, 2)

        if mode == "AUTO":
            message = (
                f"Arrosage AUTO lancé · {plan.cycles} x {plan.wago_multiplier:.1f} · "
                f"{plan.estimated_water:.1f} mm théoriques · déficit planifié "
                f"{plan.projected_deficit:.1f} -> {plan.projected_deficit_after:.1f} "
                "après confirmation WAGO."
            )
        else:
            message = (
                f"Arrosage MANUEL hydrique lancé · {plan.cycles} x {plan.wago_multiplier:.1f} · "
                f"{plan.estimated_water:.1f} mm théoriques. Le report de pluie future est ignoré, "
                "le seuil hydrique reste respecté."
            )
        self._set_text("status", message)

    def _press_wago_start(self, kwargs: dict[str, Any]) -> None:
        if self.is_on("cycle_in_progress"):
            self.call_service("button/press", entity_id=self.e("wago_start"))

    def _wago_changed(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if new == "on" and self.is_on("cycle_in_progress"):
            self._turn_on("wago_seen")
            self._set_text("status", "WAGO réellement actif : arrosage confirmé en cours.")

    def _wago_stop_pressed(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if old == new or not self.is_on("cycle_in_progress"):
            return
        self._turn_on("cycle_abandoned")
        self._set_text(
            "status",
            "STOP WAGO détecté : cycle marqué abandonné, aucune quantité forfaitaire ne sera créditée.",
        )

    def _wago_off_confirmed(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if self.is_on("cycle_in_progress"):
            self._finalize_cycle("WAGO off 20 min")

    def _finalize_cycle(self, source: str) -> None:
        confirmed = self.is_on("wago_seen") and not self.is_on("cycle_abandoned")
        water = self.number("cycle_water_planned", 0.0)
        old_credit = self.number("irrigation_credit", 0.0)
        new_credit = round(min(old_credit + (water if confirmed else 0.0), 40.0), 1)
        deficit_before = self.number("cycle_deficit_before", 0.0)
        deficit_after = self.number("cycle_deficit_after", 0.0)

        self._set_number("irrigation_credit", new_credit)
        self.call_service("number/set_value", entity_id=self.e("wago_cycles"), value=0)
        self.call_service("number/set_value", entity_id=self.e("wago_multiplier"), value=0)
        self._turn_off("cycle_in_progress")
        self._turn_off("wago_seen")
        self._turn_off("cycle_abandoned")

        if confirmed:
            self._set_text(
                "status",
                f"Arrosage terminé et confirmé · {water:.1f} mm théoriques ajoutés au crédit hydrique · "
                f"déficit planifié {deficit_before:.1f} -> {deficit_after:.1f} mm · "
                f"crédit total {new_credit:.1f} mm.",
            )
        else:
            self._set_text(
                "status",
                "Cycle terminé sans quantité créditée : démarrage WAGO non confirmé ou cycle abandonné.",
            )
        self.log(f"Cycle finalized ({source}); credited={water if confirmed else 0:.1f} mm")

    # ------------------------------------------------------------------
    # Test, recalibration and five-minute recovery
    # ------------------------------------------------------------------

    def _test_calculation(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if old == new:
            return
        plan = self._refresh_forecast()
        rain_note = " · report pluie demain" if plan.postpone_for_rain else ""
        self._set_text(
            "status",
            f"Test · déficit mémoire {self.number('deficit', 0):.1f} · "
            f"crédit eau {self.number('irrigation_credit', 0):.1f} · "
            f"ETc {plan.etc_today:.1f} · pluie eff. {plan.effective_rain_today:.1f} · "
            f"déficit prévu {plan.projected_deficit:.1f} · "
            f"{plan.cycles} x {plan.wago_multiplier:.1f} = {plan.estimated_water:.1f} mm"
            f"{rain_note}.",
        )

    def _wet_soil_recalibration(
        self,
        entity: str,
        attribute: str,
        old: Any,
        new: Any,
        kwargs: dict[str, Any],
    ) -> None:
        if old == new:
            return
        target = self.number("target_after_irrigation", 2.0)
        self._set_number("deficit", target)
        self._set_number("irrigation_credit", 0)
        self._set_text(
            "status",
            f"Recalage manuel sol humide · déficit fixé à la cible {target:.1f} mm · "
            "crédit arrosage remis à zéro.",
        )
        self._refresh_forecast()

    def _surveillance(self, kwargs: dict[str, Any]) -> None:
        if not self.is_on("cycle_in_progress"):
            self._refresh_forecast()

        self._maybe_daily_balance("surveillance 5 min")

        if (
            self.is_on("cycle_in_progress")
            and self.is_on("wago_active")
            and not self.is_on("wago_seen")
        ):
            self._turn_on("wago_seen")

        if (
            self.is_on("cycle_in_progress")
            and self.is_on("wago_seen")
            and not self.is_on("wago_active")
        ):
            wago_state = self.get_state(self.e("wago_active"), attribute="all") or {}
            changed = self._parse_datetime(wago_state.get("last_changed"))
            if changed is None:
                return

            now = self.datetime()
            if changed.tzinfo is not None and now.tzinfo is None:
                changed = changed.replace(tzinfo=None)
            elif changed.tzinfo is None and now.tzinfo is not None:
                changed = changed.replace(tzinfo=now.tzinfo)

            if (now - changed).total_seconds() >= 1200:
                self._finalize_cycle("5 min recovery")
