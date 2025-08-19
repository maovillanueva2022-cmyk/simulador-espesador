#!/usr/bin/env python
# coding: utf-8

# In[37]:


#!/usr/bin/env python
# coding: utf-8

import math
import pandas as pd
import streamlit as st
from fpdf import FPDF
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# =============================================================================
# DEFINICIÓN DE DATOS GLOBALES
# =============================================================================
ASME_B36_10M_SCH40 = {
    0.5: 15.79, 0.75: 20.93, 1: 26.64, 1.25: 35.05, 1.5: 40.89, 2: 52.5, 2.5: 62.71, 3: 77.92, 3.5: 90.12, 4: 102.26, 5: 128.19, 6: 154.05, 8: 202.72, 10: 254.51, 12: 303.22, 14: 333.38, 16: 381, 18: 428.62, 20: 477.82, 22: 523.88, 24: 571.5, 30: 711.2, 36: 850.9, 42: 1047.74, 48: 1200.14, 54: 1352.54, 60: 1504.94
}

# =============================================================================
# CLASE THICKENER Y LÓGICA DE CÁLCULO
# =============================================================================
class Thickener:
    VELOCIDAD_OBJETIVO_FLOC = 2.5; VELOCIDAD_MINIMA_UF = 1.2; VELOCIDAD_OBJETIVO_OF = 1.0; COEFICIENTE_DESCARGA_VENTANA = 0.61; GRAVEDAD = 9.81
    def __init__(self, solids_mass_flow, feed_solids_percent, solids_sg, liquor_sg, thickener_diameter, uf_solids_percent, floc_dosage, floc_solution_concentration, num_dosing_points, num_overflow_pipes, rake_tip_speed, k_factor_imperial, central_column_diameter, tank_wall_height, tank_floor_slope, num_dilution_windows, target_diluted_percent=None):
        self.solids_mass_flow = solids_mass_flow; self.feed_solids_percent = feed_solids_percent / 100.0; self.solids_sg = solids_sg; self.liquor_sg = liquor_sg; self.thickener_diameter = thickener_diameter; self.uf_solids_percent = uf_solids_percent / 100.0; self.floc_dosage = floc_dosage; self.floc_solution_concentration = floc_solution_concentration; self.num_dosing_points = num_dosing_points; self.num_overflow_pipes = num_overflow_pipes; self.rake_tip_speed = rake_tip_speed; self.k_factor_imperial = k_factor_imperial; self.central_column_diameter = central_column_diameter / 1000.0; self.tank_wall_height = tank_wall_height; self.tank_floor_slope = tank_floor_slope; self.num_dilution_windows = num_dilution_windows; self.target_diluted_percent = target_diluted_percent / 100.0 if target_diluted_percent else None
    def calculate_dilution_windows(self, dilution_flow_m3h):
        if not dilution_flow_m3h or self.num_dilution_windows == 0: return {}
        window_results = {}; delta_h = 0.1; total_flow_m3s = dilution_flow_m3h / 3600; total_area_m2 = total_flow_m3s / (self.COEFICIENTE_DESCARGA_VENTANA * math.sqrt(2 * self.GRAVEDAD * delta_h)); area_per_window_m2 = total_area_m2 / self.num_dilution_windows; height_m = math.sqrt(area_per_window_m2 / 1.5); width_m = height_m * 1.5
        window_results['Numero de Ventanas de Dilucion'] = self.num_dilution_windows; window_results['Ancho Ventana (mm)'] = width_m * 1000; window_results['Alto Ventana (mm)'] = height_m * 1000; return window_results
    def calculate_thickener_volume(self):
        volume_results = {}; tank_radius = self.thickener_diameter / 2; tank_area = math.pi * tank_radius**2; cyl_volume = tank_area * self.tank_wall_height; slope_rad = math.radians(self.tank_floor_slope); cone_height = tank_radius * math.tan(slope_rad); cone_volume = (1/3) * tank_area * cone_height; total_volume = cyl_volume + cone_volume
        volume_results['Altura Cono (m)'] = cone_height; volume_results['Volumen Cilindro (m3)'] = cyl_volume; volume_results['Volumen Cono (m3)'] = cone_volume; volume_results['Volumen Total Espesador (m3)'] = total_volume; return volume_results
    def calculate_rake_mechanics(self):
        rake_results = {}; rpm = self.rake_tip_speed / (math.pi * self.thickener_diameter); K_CONVERSION_FACTOR = 14.5939; torque_nm = (self.k_factor_imperial * K_CONVERSION_FACTOR) * (self.thickener_diameter**2); angular_velocity_rad_s = rpm * 2 * math.pi / 60; power_kw = (torque_nm * angular_velocity_rad_s) / 1000
        rake_results['Velocidad de Rotacion (RPM)'] = rpm; rake_results['Torque Requerido (Nm)'] = torque_nm; rake_results['Potencia Accionamiento (kW)'] = power_kw; return rake_results
    def calculate_flocculant(self):
        results = {}; floc_consumption_kg_h = (self.solids_mass_flow * self.floc_dosage) / 1000.0; concentration_kg_m3 = self.floc_solution_concentration * 10; total_floc_solution_flow_m3_h = floc_consumption_kg_h / concentration_kg_m3 if concentration_kg_m3 > 0 else 0
        results['Consumo Floculante (kg/h)'] = floc_consumption_kg_h; results['Caudal Solucion Floculante Total (m3/h)'] = total_floc_solution_flow_m3_h; results['Numero de Puntos de Dosificacion'] = self.num_dosing_points
        if self.num_dosing_points > 0:
            flow_per_pipe_m3h = total_floc_solution_flow_m3_h / self.num_dosing_points; flow_per_pipe_m3s = flow_per_pipe_m3h / 3600; required_area = flow_per_pipe_m3s / self.VELOCIDAD_OBJETIVO_FLOC; theoretical_diameter_m = 2 * math.sqrt(required_area / math.pi); standard_diameter_m = self.select_standard_pipe_size(theoretical_diameter_m * 1000)
            if standard_diameter_m:
                final_velocity = flow_per_pipe_m3s / (math.pi * (standard_diameter_m / 2)**2); results.update({'Caudal por Punto de Dosificacion (m3/h)': flow_per_pipe_m3h, 'Diametro Tuberia Dosificacion (mm)': standard_diameter_m * 1000, 'Velocidad en Tuberia Dosificacion (m/s)': final_velocity})
        return results
    def calculate_overflow(self, scenario_results):
        overflow_results = {}; slurry_mass_flow = self.solids_mass_flow / self.feed_solids_percent; water_in_feed = slurry_mass_flow * (1 - self.feed_solids_percent); uf_mass_flow = self.solids_mass_flow / self.uf_solids_percent; water_in_uf = uf_mass_flow * (1 - self.uf_solids_percent); total_liquid_in = water_in_feed + scenario_results.get('Agua de Dilucion Requerida (m3/h)', 0) + scenario_results.get('Caudal Solucion Floculante Total (m3/h)', 0); overflow_m3h = total_liquid_in - water_in_uf
        overflow_results['Caudal de Rebose (m3/h)'] = overflow_m3h; weir_length = math.pi * self.thickener_diameter; launder_loading = overflow_m3h / weir_length if weir_length > 0 else 0; overflow_results['Carga Hidraulica Launder (m3/h/m)'] = launder_loading; v_notch_specs = self.calculate_v_notch_launder(overflow_m3h); launder_channel_dims = self.calculate_launder_channel(overflow_m3h); overflow_results.update(v_notch_specs); overflow_results.update(launder_channel_dims)
        if self.num_overflow_pipes > 0:
            flow_per_pipe_m3s = (overflow_m3h / self.num_overflow_pipes) / 3600; required_area = flow_per_pipe_m3s / self.VELOCIDAD_OBJETIVO_OF; theoretical_diameter_m = 2 * math.sqrt(required_area / math.pi); standard_diameter_m = self.select_standard_pipe_size(theoretical_diameter_m * 1000)
            if standard_diameter_m:
                final_velocity = flow_per_pipe_m3s / (math.pi * (standard_diameter_m / 2)**2); overflow_results.update({'Numero de Tuberias de Rebose': self.num_overflow_pipes, 'Diametro Tuberia Rebose (mm)': standard_diameter_m * 1000, 'Velocidad en Tuberia Rebose (m/s)': final_velocity})
        return overflow_results
    def calculate_v_notch_launder(self, overflow_m3h):
        v_notch_results = {}; C_d, angle_deg, head_m = 0.6, 90, 0.140; angle_rad = math.radians(angle_deg); flow_per_notch_m3s = (8/15) * C_d * math.tan(angle_rad / 2) * math.sqrt(2 * self.GRAVEDAD) * (head_m**2.5); total_flow_m3s = overflow_m3h / 3600
        if flow_per_notch_m3s > 0:
            num_notches = math.ceil(total_flow_m3s / flow_per_notch_m3s); weir_length_m = math.pi * self.thickener_diameter; spacing_mm = (weir_length_m / num_notches) * 1000 if num_notches > 0 else 0; v_notch_results.update({'Diseno Launder': "V-Notch", 'Angulo V-Notch (grados)': angle_deg, 'Carga sobre V-Notch (mm)': head_m * 1000, 'Numero de Notches Requeridos': num_notches, 'Espaciamiento entre Notches (mm)': spacing_mm})
        return v_notch_results
    def calculate_launder_channel(self, overflow_m3h):
        launder_results = {}
        if self.num_overflow_pipes > 0:
            max_flow_in_launder_m3s = (overflow_m3h / self.num_overflow_pipes) / 3600; target_velocity_ms = 0.5; required_area_m2 = max_flow_in_launder_m3s / target_velocity_ms; water_height_m = math.sqrt(required_area_m2 / 2) if required_area_m2 > 0 else 0; channel_width_m = water_height_m * 2; launder_results['Ancho Canal Colector Launder (mm)'] = channel_width_m * 1000; launder_results['Altura Agua Canal Launder (mm)'] = water_height_m * 1000
        return launder_results
    def calculate_underflow_pipes(self, total_uf_flow_m3h):
        num_pipes = 2; flow_per_pipe_m3s = (total_uf_flow_m3h / num_pipes) / 3600; required_area = flow_per_pipe_m3s / self.VELOCIDAD_MINIMA_UF; theoretical_diameter_m = 2 * math.sqrt(required_area / math.pi); standard_diameter_m = self.select_standard_pipe_size(theoretical_diameter_m * 1000); pipe_results = {}
        if standard_diameter_m:
            final_velocity = flow_per_pipe_m3s / (math.pi * (standard_diameter_m / 2)**2); pipe_results.update({'Numero de Tuberias de Descarga': num_pipes, 'Diametro Tuberia Descarga (mm)': standard_diameter_m * 1000, 'Velocidad en Tuberia Descarga (m/s)': final_velocity})
        return pipe_results
    def calculate_scenario(self, floc_results, is_diluted=False):
        results = {}; slurry_mass_flow = self.solids_mass_flow / self.feed_solids_percent; results['Flujo de Alimentacion (t/h)'] = slurry_mass_flow; feed_slurry_sg = 1 / ((self.feed_solids_percent / self.solids_sg) + ((1 - self.feed_solids_percent) / self.liquor_sg)); feed_slurry_vol_flow = slurry_mass_flow / feed_slurry_sg; results['Flujo Volumetrico de Pulpa Original (m3/h)'] = feed_slurry_vol_flow; results['Densidad Pulpa Original (t/m3)'] = feed_slurry_sg; dilution_water_vol = 0
        if is_diluted and self.target_diluted_percent:
            total_mass_diluted = self.solids_mass_flow / self.target_diluted_percent; dilution_water_mass = total_mass_diluted - slurry_mass_flow; dilution_water_vol = dilution_water_mass / self.liquor_sg; results['Agua de Dilucion Requerida (m3/h)'] = dilution_water_vol
        total_feedwell_flow = feed_slurry_vol_flow + dilution_water_vol + floc_results.get('Caudal Solucion Floculante Total (m3/h)', 0); results['Flujo Volumetrico Total en Feedwell (m3/h)'] = total_feedwell_flow; thickener_area = math.pi * (self.thickener_diameter / 2)**2; results['Area del Espesador (m2)'] = thickener_area; results['Tasa de Ascenso (m/h)'] = total_feedwell_flow / thickener_area if thickener_area > 0 else 0; results['Carga de Solidos (t/m2/h)'] = self.solids_mass_flow / thickener_area if thickener_area > 0 else 0; target_residence_time_s = 47.5; dh_ratio = 6.0; vol_flow_m3_s = total_feedwell_flow / 3600; d_fw_cubed = (target_residence_time_s * vol_flow_m3_s * 24) / math.pi; theoretical_diameter_m = d_fw_cubed**(1/3) if d_fw_cubed >= 0 else 0; results['Diametro Feedwell Teorico (mm)'] = theoretical_diameter_m * 1000; adjusted_diameter_mm = math.ceil((theoretical_diameter_m * 1000) / 500) * 500; adjusted_diameter_m = adjusted_diameter_mm / 1000; results['Diametro Feedwell Ajustado (mm)'] = adjusted_diameter_mm; adjusted_height_m = adjusted_diameter_m / dh_ratio if dh_ratio > 0 else 0; results['Altura Feedwell Ajustada (mm)'] = adjusted_height_m * 1000; gross_volume_m3 = (math.pi * adjusted_diameter_m**2 / 4) * adjusted_height_m; column_volume_m3 = (math.pi * self.central_column_diameter**2 / 4) * adjusted_height_m; net_volume_m3 = gross_volume_m3 - column_volume_m3; actual_residence_time_s = net_volume_m3 / vol_flow_m3_s if vol_flow_m3_s > 0 else 0; results['Volumen Neto Feedwell (m3)'] = net_volume_m3; results['Tiempo Residencia Real (s)'] = actual_residence_time_s; uf_pulp_sg = 1 / ((self.uf_solids_percent / self.solids_sg) + ((1 - self.uf_solids_percent) / self.liquor_sg)); uf_mass_flow = self.solids_mass_flow / self.uf_solids_percent; uf_rate = uf_mass_flow / uf_pulp_sg; results['Flujo Volumetrico de Descarga (m3/h)'] = uf_rate; results['Densidad Descarga (t/m3)'] = uf_pulp_sg; return results
    def run_comparison(self):
        rake_results = self.calculate_rake_mechanics(); floc_results = self.calculate_flocculant(); volume_results = self.calculate_thickener_volume(); results_no_dilution = self.calculate_scenario(floc_results, is_diluted=False); overflow_results = self.calculate_overflow(results_no_dilution); uf_pipe_results = self.calculate_underflow_pipes(results_no_dilution['Flujo Volumetrico de Descarga (m3/h)']); vol_flow_m3_per_sec = results_no_dilution['Flujo Volumetrico de Pulpa Original (m3/h)'] / 3600; standard_diameter_m = self.select_standard_pipe_size((2 * math.sqrt((vol_flow_m3_per_sec / 1.85) / math.pi)) * 1000 if vol_flow_m3_per_sec > 0 else 0)
        results_no_dilution.update(rake_results); results_no_dilution.update(floc_results); results_no_dilution.update(overflow_results); results_no_dilution.update(uf_pipe_results); results_no_dilution.update(volume_results)
        if standard_diameter_m:
            results_no_dilution['Diametro Tuberia Estandar (mm)'] = standard_diameter_m * 1000; final_area = math.pi * (standard_diameter_m / 2)**2; results_no_dilution['Velocidad en Tuberia Final (m/s)'] = vol_flow_m3_per_sec / final_area if final_area > 0 else 0
        df_no_dilution = pd.DataFrame.from_dict(results_no_dilution, orient='index', columns=['Escenario: Sin Dilucion'])
        if self.target_diluted_percent:
            results_with_dilution = self.calculate_scenario(floc_results, is_diluted=True); overflow_results_diluted = self.calculate_overflow(results_with_dilution); dilution_window_results = self.calculate_dilution_windows(results_with_dilution.get('Agua de Dilucion Requerida (m3/h)', 0)); results_with_dilution.update(overflow_results_diluted); results_with_dilution.update(dilution_window_results)
            results_with_dilution.update({'Diametro Tuberia Estandar (mm)': results_no_dilution.get('Diametro Tuberia Estandar (mm)'), 'Velocidad en Tuberia Final (m/s)': results_no_dilution.get('Velocidad en Tuberia Final (m/s)'), **rake_results, **floc_results, **uf_pipe_results, **volume_results})
            df_with_dilution = pd.DataFrame.from_dict(results_with_dilution, orient='index', columns=['Escenario: Con Dilucion']); df_final = df_no_dilution.join(df_with_dilution, how='outer')
        else: df_final = df_no_dilution
        return df_final.fillna('-')
    def select_standard_pipe_size(self, required_diameter_mm):
        if required_diameter_mm is None or required_diameter_mm <= 0: return None
        for nps, inner_dia_mm in sorted(ASME_B36_10M_SCH40.items()):
            if inner_dia_mm >= required_diameter_mm: return inner_dia_mm / 1000.0
        return max(ASME_B36_10M_SCH40.values()) / 1000.0

# ... (Las clases y funciones de reportes PDF y PPTX se omiten aquí por brevedad)

# =============================================================================
# FUNCIONES DE VISUALIZACIÓN Y GRÁFICOS
# =============================================================================
# (La función de Plotly permanece aquí)

# =============================================================================
# INTERFAZ PRINCIPAL DE STREAMLIT
# =============================================================================
st.set_page_config(layout="wide")
st.title("Simulador de Diseño de Espesadores ⚙️")

with st.sidebar:
    try:
        st.image("tu_logo.png", width=150)
    except FileNotFoundError:
        st.write("Logo no encontrado.")
    
    st.header("Parámetros de Entrada")
    
    with st.expander("Proceso y Alimentación", expanded=True):
        solids_mass_flow = st.number_input("Flujo de sólidos (t/h)", min_value=0.1, value=3000.0, step=100.0)
        feed_solids_percent = st.number_input("Sólidos en alimentación (%)", min_value=0.1, max_value=100.0, value=30.0)
        uf_solids_percent = st.number_input("Sólidos en descarga (%)", min_value=0.1, max_value=100.0, value=60.0)
        solids_sg = st.number_input("Gravedad específica (SG) de sólidos", min_value=0.1, value=4.7)
        liquor_sg = st.number_input("Gravedad específica (SG) del líquido", min_value=0.1, value=1.0)
    
    with st.expander("Diseño del Tanque y Tuberías", expanded=True):
        thickener_diameter = st.number_input("Diámetro del espesador (m)", min_value=1.0, value=63.0)
        central_column_diameter = st.number_input("Diámetro de columna central (mm)", min_value=0.0, value=2000.0)
        tank_wall_height = st.number_input("Altura de pared del tanque (m)", min_value=0.1, value=5.0)
        tank_floor_slope = st.number_input("Ángulo del piso (grados)", min_value=0.0, max_value=45.0, value=8.0)
        num_overflow_pipes = st.number_input("Número de tuberías de rebose", min_value=0, value=4, step=1)

    with st.expander("Parámetros Mecánicos y Floculante"):
        rake_tip_speed = st.number_input("Velocidad punta de rastra (m/min)", min_value=0.1, value=8.0)
        k_factor_imperial = st.number_input("Factor K de Torque (ft-lbf/ft^2)", min_value=0.0, value=100.0)
        floc_dosage = st.number_input("Dosis de floculante (g/t)", min_value=0.0, value=30.0)
        floc_solution_concentration = st.number_input("Concentración de floculante (% p/v)", min_value=0.01, value=0.1)
        num_dosing_points = st.number_input("Puntos de dosificación de floculante", min_value=0, value=3, step=1)
    
    with st.expander("Opciones de Dilución"):
        wants_dilution = st.checkbox("Calcular escenario con dilución", value=True)
        target_diluted_percent = None; num_dilution_windows = 0
        if wants_dilution:
            target_diluted_percent = st.number_input("% sólidos objetivo para dilución", min_value=0.1, max_value=100.0, value=15.0)
            num_dilution_windows = st.number_input("Número de ventanillas de dilución", min_value=0, value=4, step=1)

st.info("⚙️ Configure los parámetros en el panel izquierdo y haga clic en 'Calcular Diseño' para generar la simulación.")
st.markdown("---")

if st.button("Calcular Diseño"):
    if thickener_diameter <= 0 or solids_mass_flow <= 0:
        st.error("Error: El diámetro del espesador y el flujo de sólidos deben ser mayores que cero.")
    else:
        with st.spinner('Realizando cálculos...'):
            user_inputs = {'solids_mass_flow': solids_mass_flow, 'feed_solids_percent': feed_solids_percent,'solids_sg': solids_sg, 'liquor_sg': liquor_sg, 'thickener_diameter': thickener_diameter,'uf_solids_percent': uf_solids_percent, 'floc_dosage': floc_dosage,'floc_solution_concentration': floc_solution_concentration, 'num_dosing_points': num_dosing_points,'num_overflow_pipes': num_overflow_pipes, 'rake_tip_speed': rake_tip_speed,'k_factor_imperial': k_factor_imperial, 'central_column_diameter': central_column_diameter,'tank_wall_height': tank_wall_height, 'tank_floor_slope': tank_floor_slope,'num_dilution_windows': num_dilution_windows, 'target_diluted_percent': target_diluted_percent}
            
            thickener_calculator = Thickener(**user_inputs)
            final_report_df = thickener_calculator.run_comparison()
            df_display = final_report_df.applymap(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
            
            st.header("Resultados de la Simulación")
            st.subheader("Indicadores Claves de Diseño")
            kpi_cols_1 = st.columns(4); kpi_cols_2 = st.columns(4)
            scenario_to_show = 'Escenario: Con Dilucion' if wants_dilution and 'Escenario: Con Dilucion' in final_report_df.columns else 'Escenario: Sin Dilucion'
            kpi_data = final_report_df[scenario_to_show]
            
            kpi_cols_1[0].metric("Torque de Diseño", f"{pd.to_numeric(kpi_data.get('Torque Requerido (Nm)', 0)):,.0f} Nm")
            kpi_cols_1[1].metric("Diámetro del Equipo", f"{thickener_diameter} m")
            kpi_cols_1[2].metric("Volumen Total", f"{pd.to_numeric(kpi_data.get('Volumen Total Espesador (m3)', 0)):,.0f} m³")
            kpi_cols_1[3].metric("Flujo de Sólidos", f"{user_inputs['solids_mass_flow']:,.0f} t/h")
            kpi_cols_2[0].metric("Carga de Sólidos", f"{pd.to_numeric(kpi_data.get('Carga de Solidos (t/m2/h)', 0)):.2f} t/m²/h")
            kpi_cols_2[1].metric("Tasa de Ascenso", f"{pd.to_numeric(kpi_data.get('Tasa de Ascenso (m/h)', 0)):.2f} m/h")
            kpi_cols_2[2].metric("Potencia Accionamiento", f"{pd.to_numeric(kpi_data.get('Potencia Accionamiento (kW)', 0)):.2f} kW")
            st.markdown("---")
            
            st.subheader("Análisis Comparativo Interactivo")
            fig_plotly = generar_grafico_comparativo_plotly(final_report_df)
            if fig_plotly:
                st.plotly_chart(fig_plotly, use_container_width=True)
            
            st.header("Tablas de Resultados")
            process_keys = ['Altura Cono (m)', 'Volumen Cilindro (m3)', 'Volumen Cono (m3)', 'Volumen Total Espesador (m3)', 'Flujo de Alimentacion (t/h)', 'Flujo Volumetrico de Pulpa Original (m3/h)', 'Densidad Pulpa Original (t/m3)', 'Agua de Dilucion Requerida (m3/h)', 'Flujo Volumetrico Total en Feedwell (m3/h)', 'Area del Espesador (m2)', 'Tasa de Ascenso (m/h)', 'Carga de Solidos (t/m2/h)', 'Flujo Volumetrico de Descarga (m3/h)', 'Densidad Descarga (t/m3)','Consumo Floculante (kg/h)', 'Caudal Solucion Floculante Total (m3/h)','Diametro Feedwell Teorico (mm)', 'Diametro Feedwell Ajustado (mm)', 'Altura Feedwell Ajustada (mm)','Volumen Neto Feedwell (m3)', 'Tiempo Residencia Real (s)', 'Caudal de Rebose (m3/h)', 'Carga Hidraulica Launder (m3/h/m)','Diseno Launder', 'Angulo V-Notch (grados)', 'Carga sobre V-Notch (mm)','Numero de Notches Requeridos', 'Espaciamiento entre Notches (mm)','Ancho Canal Colector Launder (mm)', 'Altura Agua Canal Launder (mm)','Numero de Ventanas de Dilucion', 'Ancho Ventana (mm)', 'Alto Ventana (mm)']
            df_process = df_display.loc[df_display.index.isin(process_keys)].reindex(process_keys).dropna(how='all'); st.subheader("Datos de Proceso"); st.data_editor(df_process, height=400)
            
            mechanical_keys = ['Velocidad de Rotacion (RPM)', 'Torque Requerido (Nm)', 'Potencia Accionamiento (kW)','Diametro Tuberia Estandar (mm)', 'Velocidad en Tuberia Final (m/s)','Numero de Puntos de Dosificacion', 'Caudal por Punto de Dosificacion (m3/h)','Diametro Tuberia Dosificacion (mm)', 'Velocidad en Tuberia Dosificacion (m/s)','Numero de Tuberias de Descarga', 'Diametro Tuberia Descarga (mm)','Velocidad en Tuberia Descarga (m/s)', 'Numero de Tuberias de Rebose','Diametro Tuberia Rebose (mm)', 'Velocidad en Tuberia Rebose (m/s)']
            df_mechanical = df_display.loc[df_display.index.isin(mechanical_keys)].reindex(mechanical_keys).dropna(how='all'); st.subheader("Datos Mecánicos y de Tuberías"); st.data_editor(df_mechanical, height=300)


# In[ ]:




