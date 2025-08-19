#!/usr/bin/env python
# coding: utf-8

# In[34]:


#!/usr/bin/env python
# coding: utf-8

import math
import pandas as pd
import streamlit as st
from fpdf import FPDF, FPDFException
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import BytesIO

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

# =============================================================================
# CLASES Y FUNCIONES PARA REPORTES PDF
# =============================================================================
class PDF_Resumen(FPDF):
    def header(self):
        try: self.image("tu_logo.png", 10, 8, 33)
        except RuntimeError: self.set_font('Arial', 'B', 12); self.cell(40, 10, 'Mi Empresa', 1, 0, 'C')
        self.set_font('Arial', 'B', 15); self.cell(80); self.cell(30, 10, 'Reporte de Diseño de Espesador', 0, 0, 'C'); self.set_font('Arial', '', 10); self.cell(80, 10, f"Fecha: {datetime.now().strftime('%d-%m-%Y')}", 0, 1, 'R'); self.ln(20)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C'); self.cell(0, 10, 'Documento Confidencial', 0, 0, 'R')
    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12); self.cell(0, 10, title, 0, 1, 'L'); self.ln(4)
    def chapter_body(self, data, is_dict=False):
        self.set_font('Arial', '', 10)
        if is_dict:
            for key, val in data.items():
                val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val); self.cell(95, 6, f"{key}:", 1); self.cell(95, 6, val_str, 1); self.ln()
        else:
            self.set_font('Arial', 'B', 10); self.set_fill_color(220, 220, 220); header = list(data.columns); col_widths = {'Parámetro': 80, 'Escenario: Sin Dilucion': 55, 'Escenario: Con Dilucion': 55}; self.cell(col_widths['Parámetro'], 7, 'Parámetro', 1, 0, 'C', 1)
            for col in header: self.cell(col_widths.get(col, 55), 7, col, 1, 0, 'C', 1)
            self.ln(); self.set_font('Arial', '', 9); fill = False
            for idx, row in data.iterrows():
                self.set_fill_color(245, 245, 245); self.cell(col_widths['Parámetro'], 6, str(idx), 1, 0, 'L', fill)
                for col in header: self.cell(col_widths.get(col, 55), 6, str(row[col]), 1, 0, 'R', fill)
                self.ln(); fill = not fill
        self.ln(10)

def create_summary_pdf_report(inputs, results_df):
    try:
        pdf = PDF_Resumen(); pdf.add_page(); formatted_inputs = {k.replace('_', ' ').title(): v for k, v in inputs.items()}; pdf.chapter_title('Parámetros de Entrada'); pdf.chapter_body(formatted_inputs, is_dict=True)
        process_keys = ['Altura Cono (m)', 'Volumen Cilindro (m3)', 'Volumen Cono (m3)', 'Volumen Total Espesador (m3)', 'Flujo de Alimentacion (t/h)', 'Flujo Volumetrico de Pulpa Original (m3/h)', 'Densidad Pulpa Original (t/m3)', 'Agua de Dilucion Requerida (m3/h)', 'Flujo Volumetrico Total en Feedwell (m3/h)', 'Area del Espesador (m2)', 'Tasa de Ascenso (m/h)', 'Carga de Solidos (t/m2/h)', 'Flujo Volumetrico de Descarga (m3/h)', 'Densidad Descarga (t/m3)','Consumo Floculante (kg/h)', 'Caudal Solucion Floculante Total (m3/h)','Diametro Feedwell Teorico (mm)', 'Diametro Feedwell Ajustado (mm)', 'Altura Feedwell Ajustada (mm)','Volumen Neto Feedwell (m3)', 'Tiempo Residencia Real (s)', 'Caudal de Rebose (m3/h)', 'Carga Hidraulica Launder (m3/h/m)','Diseno Launder', 'Angulo V-Notch (grados)', 'Carga sobre V-Notch (mm)','Numero de Notches Requeridos', 'Espaciamiento entre Notches (mm)','Ancho Canal Colector Launder (mm)', 'Altura Agua Canal Launder (mm)','Numero de Ventanas de Dilucion', 'Ancho Ventana (mm)', 'Alto Ventana (mm)']
        mechanical_keys = ['Velocidad de Rotacion (RPM)', 'Torque Requerido (Nm)', 'Potencia Accionamiento (kW)','Diametro Tuberia Estandar (mm)', 'Velocidad en Tuberia Final (m/s)','Numero de Puntos de Dosificacion', 'Caudal por Punto de Dosificacion (m3/h)','Diametro Tuberia Dosificacion (mm)', 'Velocidad en Tuberia Dosificacion (m/s)','Numero de Tuberias de Descarga', 'Diametro Tuberia Descarga (mm)','Velocidad en Tuberia Descarga (m/s)', 'Numero de Tuberias de Rebose','Diametro Tuberia Rebose (mm)', 'Velocidad en Tuberia Rebose (m/s)']
        df_process = results_df.loc[results_df.index.isin(process_keys)].reindex(process_keys).dropna(how='all'); df_mechanical = results_df.loc[results_df.index.isin(mechanical_keys)].reindex(mechanical_keys).dropna(how='all')
        pdf.add_page(); pdf.chapter_title('Resultados de Proceso'); pdf.chapter_body(df_process); pdf.chapter_title('Resultados Mecánicos y de Tuberías'); pdf.chapter_body(df_mechanical)
        return bytes(pdf.output(dest='S'))
    except Exception as e:
        st.error(f"Error al generar PDF Resumen: {e}")
        return None

class PDF_Memoria(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16); self.cell(0, 10, 'Memoria de Cálculo: Diseño de Espesador', 0, 1, 'C'); self.set_font('Arial', '', 10); self.cell(0, 10, f"Fecha de Emisión: {datetime.now().strftime('%d-%m-%Y')}", 0, 1, 'C'); self.ln(10)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    def add_section_title(self, title):
        self.ln(5); self.set_font('Arial', 'B', 12); self.set_fill_color(230, 230, 230); self.cell(0, 10, title, 0, 1, 'L', fill=True); self.ln(4)
    def add_descriptive_text(self, text):
        self.set_font('Arial', 'I', 10); self.multi_cell(0, 5, text); self.ln(3)
    def add_nomenclature_table(self, data):
        self.set_font('Arial', 'B', 10); col_widths = (25, 125, 40); self.cell(col_widths[0], 7, 'Símbolo', 1, 0, 'C'); self.cell(col_widths[1], 7, 'Descripción', 1, 0, 'C'); self.cell(col_widths[2], 7, 'Unidades', 1, 1, 'C'); self.set_font('Arial', '', 10)
        for row in data:
            self.cell(col_widths[0], 6, row[0], 1); self.cell(col_widths[1], 6, row[1], 1); self.cell(col_widths[2], 6, row[2], 1); self.ln()
    def add_calculation_step(self, formula, substitution, result):
        with self.unbreakable() as pdf:
            pdf.set_font('Courier', 'I', 10); pdf.write(5, "Fórmula      : "); pdf.set_font('Courier', '', 10); pdf.write(5, f"{formula}\n")
            pdf.set_font('Courier', 'I', 10); pdf.write(5, "Sustitución  : "); pdf.set_font('Courier', '', 10); pdf.write(5, f"{substitution}\n")
            pdf.set_font('Courier', 'B', 10); pdf.write(5, "Resultado    : "); pdf.set_font('Courier', 'B', 10); pdf.write(5, f"{result}\n")
            pdf.ln(4)

def generar_memoria_de_calculo_pdf(inputs, results_df):
    try:
        pdf = PDF_Memoria(); pdf.add_page()
        pdf.add_section_title("1. Parámetros de Diseño de Entrada")
        for key, val in inputs.items():
            key_str = key.replace('_', ' ').title(); pdf.set_font('Arial', '', 10); pdf.cell(100, 6, key_str, border=1); pdf.cell(90, 6, str(val), border=1); pdf.ln()
        pdf.add_section_title("2. Nomenclatura y Símbolos Utilizados")
        nomenclature_data = [
            ('D', 'Diámetro del Espesador', 'm'), ('R', 'Radio del Espesador', 'm'), ('H_wall', 'Altura Pared Cilindro', 'm'),
            ('H_cone', 'Altura del Cono', 'm'), ('V_cyl', 'Volumen del Cilindro', 'm³'), ('V_cone', 'Volumen del Cono', 'm³'),
            ('V_total', 'Volumen Total Espesador', 'm³'), ('T', 'Torque del Mecanismo', 'Nm'), ('P', 'Potencia del Accionamiento', 'kW'),
            ('Q_feed', 'Caudal Vol. Alimentación', 'm³/h'), ('Q_uf', 'Caudal Vol. Descarga', 'm³/h'),
            ('Q_of', 'Caudal Vol. Rebose', 'm³/h'), ('A', 'Área Superficial Espesador', 'm²'),
        ]
        pdf.add_nomenclature_table(nomenclature_data)
        scenario = 'Escenario: Con Dilucion' if 'Escenario: Con Dilucion' in results_df.columns else 'Escenario: Sin Dilucion'; data = results_df.loc[:, scenario].apply(pd.to_numeric, errors='coerce')
        pdf.add_section_title("3. Desarrollo de Cálculos de Ingeniería")
        pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "3.1 Geometría y Volumen del Tanque", 0, 1, 'L'); pdf.add_descriptive_text("Cálculo del volumen total del espesador, sumando los volúmenes de sus secciones cilíndrica y cónica.")
        D = inputs['thickener_diameter']; R = D / 2; H_wall = inputs['tank_wall_height']; slope = inputs['tank_floor_slope']; H_cone = data['Altura Cono (m)']; V_cyl = data['Volumen Cilindro (m3)']; V_cone = data['Volumen Cono (m3)']; V_total = data['Volumen Total Espesador (m3)']
        pdf.add_calculation_step("H_cone = R * tan(ángulo)", f"H_cono = {R:.2f} m * tan({slope}°)", f"{H_cone:.2f} m")
        pdf.add_calculation_step("V_cyl = pi * R² * H_wall", f"V_cil = 3.1416 * ({R:.2f} m)² * {H_wall:.2f} m", f"{V_cyl:,.2f} m³")
        pdf.add_calculation_step("V_cone = (1/3) * pi * R² * H_cone", f"V_cono = (1/3) * 3.1416 * ({R:.2f} m)² * {H_cone:.2f} m", f"{V_cone:,.2f} m³")
        pdf.add_calculation_step("V_total = V_cyl + V_cone", f"V_total = {V_cyl:,.2f} m³ + {V_cone:,.2f} m³", f"{V_total:,.2f} m³")
        pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "3.2 Mecanismo de Rastras", 0, 1, 'L'); pdf.add_descriptive_text("Cálculo de los requerimientos mecánicos para el sistema de rastras, incluyendo velocidad de rotación, torque y potencia.")
        rpm = data['Velocidad de Rotacion (RPM)']; torque = data['Torque Requerido (Nm)']; power = data['Potencia Accionamiento (kW)']
        pdf.add_calculation_step("RPM = Velocidad_punta / (pi * D)", f"RPM = {inputs['rake_tip_speed']:.2f} m/min / (3.1416 * {D:.2f} m)", f"{rpm:.4f} RPM")
        pdf.add_calculation_step("T [Nm] = K_factor [ft-lbf/ft²] * 14.59 * D²", f"T = {inputs['k_factor_imperial']:.2f} * 14.59 * ({D:.2f} m)²", f"{torque:,.0f} Nm")
        pdf.add_calculation_step("P [kW] = (T * RPM * 2 * pi) / 60000", f"P = ({torque:,.0f} Nm * {rpm:.4f} * 2 * 3.1416) / 60000", f"{power:.2f} kW")
        pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "3.3 Parámetros Hidráulicos", 0, 1, 'L'); pdf.add_descriptive_text("Evaluación de los indicadores de rendimiento hidráulico: carga de sólidos por área y velocidad de ascenso del líquido.")
        area = data['Area del Espesador (m2)']; solid_load = data['Carga de Solidos (t/m2/h)']; rise_rate = data['Tasa de Ascenso (m/h)']
        pdf.add_calculation_step("A = pi * R²", f"A = 3.1416 * ({R:.2f} m)²", f"{area:,.2f} m²")
        pdf.add_calculation_step("Carga Sólidos = Flujo Sólidos / A", f"Carga = {inputs['solids_mass_flow']:.2f} t/h / {area:,.2f} m²", f"{solid_load:.3f} t/m²/h")
        pdf.add_calculation_step("Tasa Ascenso = Q_of / A", f"Tasa = {data['Caudal de Rebose (m3/h)']:.2f} m³/h / {area:,.2f} m²", f"{rise_rate:.3f} m/h")
        pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "3.4 Diseño del Feedwell", 0, 1, 'L'); pdf.add_descriptive_text("Cálculo del volumen neto y el tiempo de residencia de la pulpa en el feedwell, un parámetro clave para la floculación.")
        vol_neto_fw = data['Volumen Neto Feedwell (m3)']; Q_total_fw = data['Flujo Volumetrico Total en Feedwell (m3/h)']; t_residencia = data['Tiempo Residencia Real (s)']
        pdf.add_calculation_step("T_residencia [s] = V_neto [m³] / (Q_total [m³/h] / 3600)", f"T = {vol_neto_fw:.2f} m³ / ({Q_total_fw:.2f} m³/h / 3600)", f"{t_residencia:.1f} s")
        pdf.set_font('Arial', 'B', 10); pdf.cell(0, 10, "3.5 Diseño de Tubería de Alimentación", 0, 1, 'L'); pdf.add_descriptive_text("Cálculo del diámetro de la tubería de alimentación basado en el caudal de pulpa y una velocidad objetivo para evitar sedimentación (típicamente 1.5-2.0 m/s).")
        Q_alim = data['Flujo Volumetrico de Pulpa Original (m3/h)']; V_obj = 1.85; Q_alim_s = Q_alim / 3600; Area_req = Q_alim_s / V_obj; D_teorico_mm = (math.sqrt(Area_req / math.pi) * 2) * 1000 if Area_req > 0 else 0; D_estandar = data['Diametro Tuberia Estandar (mm)']
        pdf.add_calculation_step("Área_req [m²] = (Q_alim [m³/h] / 3600) / V_obj [m/s]", f"Área = ({Q_alim:.2f} / 3600) / {V_obj}", f"{Area_req:.4f} m²")
        pdf.add_calculation_step("D_teórico [mm] = sqrt(Área / pi) * 2 * 1000", f"D = sqrt({Area_req:.4f} / 3.1416) * 2 * 1000", f"{D_teorico_mm:.1f} mm")
        pdf.set_font('Arial', '', 10); pdf.multi_cell(0, 5, f"Considerando el diámetro teórico, se selecciona un diámetro de tubería estándar (ASME B36.10M) de **{D_estandar:.1f} mm**.")
        return bytes(pdf.output(dest='S'))
    except Exception as e:
        st.error(f"Error al generar Memoria de Cálculo: {e}")
        return None

# =============================================================================
# FUNCIONES DE VISUALIZACIÓN Y GRÁFICOS
# =============================================================================
def generar_grafico_comparativo_plotly(df_reporte):
    if 'Escenario: Con Dilucion' not in df_reporte.columns: return None 
    fig = make_subplots(specs=[[{"secondary_y": True}]]); metricas_eje1 = {'Flujo Total Feedwell (m³/h)': 'Flujo Volumetrico Total en Feedwell (m3/h)', 'Caudal de Rebose (m³/h)': 'Caudal de Rebose (m3/h)'}; metricas_eje2 = {'Tasa de Ascenso (m/h)': 'Tasa de Ascenso (m/h)', 'T. Residencia (s)': 'Tiempo Residencia Real (s)'}; df_eje1 = df_reporte.loc[metricas_eje1.values()].astype(float); df_eje1.index = metricas_eje1.keys(); df_eje2 = df_reporte.loc[metricas_eje2.values()].astype(float); df_eje2.index = metricas_eje2.keys()
    fig.add_trace(go.Bar(x=df_eje1.index, y=df_eje1['Escenario: Sin Dilucion'], name='Sin Dilución (Eje Izquierdo)', marker_color='crimson', text=df_eje1['Escenario: Sin Dilucion'].round(1), textposition='auto'), secondary_y=False); fig.add_trace(go.Bar(x=df_eje1.index, y=df_eje1['Escenario: Con Dilucion'], name='Con Dilución (Eje Izquierdo)', marker_color='lightcoral', text=df_eje1['Escenario: Con Dilucion'].round(1), textposition='auto'), secondary_y=False)
    fig.add_trace(go.Bar(x=df_eje2.index, y=df_eje2['Escenario: Sin Dilucion'], name='Sin Dilución (Eje Derecho)', marker_color='mediumblue', text=df_eje2['Escenario: Sin Dilucion'].round(1), textposition='auto'), secondary_y=True); fig.add_trace(go.Bar(x=df_eje2.index, y=df_eje2['Escenario: Con Dilucion'], name='Con Dilución (Eje Derecho)', marker_color='lightskyblue', text=df_eje2['Escenario: Con Dilucion'].round(1), textposition='auto'), secondary_y=True)
    fig.update_layout(title_text='<b>Impacto de la Dilución en Parámetros Clave</b>', barmode='group', template='plotly_white', legend_title_text='Escenarios y Ejes'); fig.update_yaxes(title_text="<b>Caudal (m³/h)</b>", secondary_y=False); fig.update_yaxes(title_text="<b>Tasa (m/h) / Tiempo (s)</b>", secondary_y=True)
    return fig

# =============================================================================
# INTERFAZ PRINCIPAL DE STREAMLIT
# =============================================================================
st.set_page_config(layout="wide")
st.title("Simulador de Diseño de Espesadores ⚙️")

with st.sidebar:
    try: st.image("tu_logo.png", width=150)
    except FileNotFoundError: st.write("Logo no encontrado.")
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
        with st.spinner('Realizando cálculos y generando documentos...'):
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
            
            st.header("Descargar Documentos")
            dl_cols = st.columns(2)
            with dl_cols[0]:
                pdf_summary_data = create_summary_pdf_report(user_inputs, df_display)
                st.download_button(label="📄 Descargar Reporte Resumen", data=pdf_summary_data, file_name="reporte_resumen_espesador.pdf", mime="application/pdf")
            with dl_cols[1]:
                pdf_memoria_data = generar_memoria_de_calculo_pdf(user_inputs, final_report_df)
                st.download_button(label="📝 Descargar Memoria de Cálculo", data=pdf_memoria_data, file_name="memoria_calculo_espesador.pdf", mime="application/pdf")


# In[ ]:




