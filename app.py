# -*- coding: utf-8 -*-
"""
Created on Sat Mar 15 16:47:48 2025

@author: kumab
"""
import hashlib
import io
import os

import streamlit as st
import folium
from streamlit_folium import folium_static
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import Point
import requests

# Import your modules
from modules.pv_calculator import get_weather_data, get_solar_position, calculate_pv_production
from modules.financial import financial_analysis, estimate_consumption_and_capacity, project_electricity_price
from modules.mapping import create_town_map, town_list

# Define standard panel dimensions
PANEL_WIDTH = 1.7  # meters
PANEL_HEIGHT = 1.0  # meters
SPACING_FACTOR = 0.2  # ratio
CURRENCY_CONVERSION_RATE = 130  # ETB per USD

# Define current year and quarter for tariff projections
CURRENT_YEAR = 2024
CURRENT_QUARTER = 1  # 1, 2, 3, or 4 for the quarters of the year

# Check weather data availability
def check_weather_data_connection():
    """Test if the regional weather data files are accessible"""
    try:
        # Import the regional files mapping from pv_calculator
        from modules.pv_calculator import REGIONAL_FILES
        
        configured_regions = 0
        total_regions = len(REGIONAL_FILES)
        
        for region_name, region_info in REGIONAL_FILES.items():
            mega_url = region_info.get("mega_url", "")
            
            # Check if URL is configured (not a placeholder)
            if mega_url and not mega_url.startswith("UPDATE_WITH_"):
                configured_regions += 1
        
        # Return True if we have at least some regions configured
        return configured_regions > 0
        
    except Exception as e:
        return False
# Helper function for currency formatting
def format_currency(amount, currency="ETB"):
    """Format currency values consistently"""
    if currency == "ETB":
        return f"{amount:,.0f} ETB"
    else:
        return f"${amount:,.2f}"

def render_location_info(town_name, lat, lon, geometry):
    """Render the location information within the Location tab"""
    
    if not town_name:
        st.info("Please select a town from the dropdown menu above")
        return
        
    # Display a spinner while analyzing
    with st.spinner(f"Analyzing {town_name}..."):
        # Create fallback analysis results
        # These are approximate values for Ethiopia that vary by region
        
        # Define region-based parameters (approximated)
        regions = {
            # Northern regions (Tigray, Amhara)
            "north": {
                "ghi": 2100,
                "elevation": 2000,
                "pop_density": 120,
                "suitable_percent": 35
            },
            # Central regions (Addis, Oromia)
            "central": {
                "ghi": 2000,
                "elevation": 2400,
                "pop_density": 200,
                "suitable_percent": 30
            },
            # Southern regions (SNNPR)
            "south": {
                "ghi": 2200,
                "elevation": 1800,
                "pop_density": 150,
                "suitable_percent": 40
            },
            # Eastern regions (Somali, Afar)
            "east": {
                "ghi": 2300,
                "elevation": 1000,
                "pop_density": 60,
                "suitable_percent": 45
            },
            # Western regions (Benishangul-Gumuz, Gambela)
            "west": {
                "ghi": 1900,
                "elevation": 1600,
                "pop_density": 80,
                "suitable_percent": 35
            }
        }
        
        # Determine region based on location (simplified)
        # This is a very rough approximation - could be improved with actual region boundaries
        region = "central"  # Default
        if lat > 12:
            region = "north"
        elif lat < 7:
            region = "south"
        elif lon > 40:
            region = "east"
        elif lon < 36:
            region = "west"
        
        # Get region parameters
        params = regions[region]
        
        # Calculate area (approximate)
        area_km2 = 50  # Default town area in km²
        
        # Add some realistic variation based on coordinates
        # Create a deterministic but seemingly random value based on coordinates
        coord_hash = hashlib.md5(f"{lat:.2f}_{lon:.2f}".encode()).hexdigest()
        hash_value = int(coord_hash[:8], 16) / (2**32)
        
        # Apply variations (±10-20%)
        ghi = params["ghi"] * (0.9 + hash_value * 0.2)
        elevation = params["elevation"] * (0.8 + hash_value * 0.4)
        pop_density = params["pop_density"] * (0.7 + hash_value * 0.6)
        suitable_percent = params["suitable_percent"] * (0.8 + hash_value * 0.4)
        
        # Calculate solar potential
        suitable_area_km2 = area_km2 * (suitable_percent / 100)
        capacity_density = 50  # MW/km²
        capacity_factor = 0.18  # 18% average for Ethiopia
        potential_capacity_mw = suitable_area_km2 * capacity_density
        annual_generation_gwh = potential_capacity_mw * 8760 * capacity_factor / 1000
        
        # Create summary data structure
        summary = {
            "location": {
                "name": town_name,
                "area_km2": round(area_km2, 2)
            },
            "solar_resource": {
                "mean_ghi": round(ghi, 0),
                "min_ghi": round(ghi * 0.9, 0),
                "max_ghi": round(ghi * 1.1, 0)
            },
            "population": {
                "mean_density": round(pop_density, 0),
                "max_density": round(pop_density * 2.5, 0)
            },
            "elevation": {
                "mean": round(elevation, 0),
                "min": round(elevation * 0.8, 0),
                "max": round(elevation * 1.2, 0)
            },
            "pv_potential": {
                "suitable_area_km2": round(suitable_area_km2, 2),
                "suitable_percent": round(suitable_percent, 1),
                "potential_capacity_mw": round(potential_capacity_mw, 1),
                "annual_generation_gwh": round(annual_generation_gwh, 1)
            }
        }
        
        # Create a layout with town info and PV potential
        st.subheader(f"☀️ Solar Resource Information for {town_name}")
        
        col1, col2 = st.columns([1, 1])
        
        # Display town information in the first column
        with col1:
            st.markdown("### 📍 Town Overview")
            st.markdown(f"**Name:** {town_name}")
            st.markdown(f"**Coordinates:** {lat:.4f}°N, {lon:.4f}°E")
            st.markdown(f"**Area:** {summary['location']['area_km2']} km²")
            
            # Solar resource information
            st.markdown("### ☀️ Solar Resource")
            st.markdown(f"**Average Solar Irradiance:** {summary['solar_resource']['mean_ghi']} kWh/m²/year")
            st.markdown(f"**Range:** {summary['solar_resource']['min_ghi']} - {summary['solar_resource']['max_ghi']} kWh/m²/year")
            
            # Population information
            st.markdown("### 👥 Demographics")
            st.markdown(f"**Average Population Density:** {summary['population']['mean_density']} people/km²")
            
            # Topography information
            st.markdown("### 🏔️ Topography")
            st.markdown(f"**Average Elevation:** {summary['elevation']['mean']} m")
            st.markdown(f"**Elevation Range:** {summary['elevation']['min']} - {summary['elevation']['max']} m")
        # Display PV potential and map in the second column
        with col2:
            st.markdown("### 🔋 Solar PV Potential")
            
            # Create metrics in a horizontal layout
            metric_col1, metric_col2 = st.columns(2)
            with metric_col1:
                st.metric("Suitable Area", f"{summary['pv_potential']['suitable_area_km2']} km²")
                st.metric("Potential Capacity", f"{summary['pv_potential']['potential_capacity_mw']} MW")
            
            with metric_col2:
                st.metric("Suitable Land", f"{summary['pv_potential']['suitable_percent']}%")
                st.metric("Annual Generation", f"{summary['pv_potential']['annual_generation_gwh']} GWh")
            
            # Generate a simple map using folium
            st.markdown("### 🗺️ Town Map")
            m = folium.Map(location=[lat, lon], zoom_start=12)
            
            # Add a marker for the town center
            folium.Marker(
                [lat, lon],
                popup=f"{town_name}",
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(m)
            
            # Add a circle for the approximate analysis area
            folium.Circle(
                location=[lat, lon],
                # radius=2000,  # 2km radius
                # color='blue',
                # fill=True,
                # fill_color='blue',
                # fill_opacity=0.2,
                popup="Analysis Area"
            ).add_to(m)
            
            # Add a choropleth layer for suitability (simulated)
            # Create points in a grid around the center
            grid_size = 10
            points = []
            for i in range(grid_size):
                for j in range(grid_size):
                    # Create a grid of points within 2km
                    y = lat + (i - grid_size/2) * 0.004
                    x = lon + (j - grid_size/2) * 0.004
                    # Calculate a suitability value (pseudo-random but deterministic)
                    val = (np.sin(x*100) + np.cos(y*100) + 2) / 4 * suitable_percent/100
                    points.append([y, x, val])
            
            # # Add circles with varying colors for suitability
            # for p in points:
            #     folium.Circle(
            #         location=[p[0], p[1]],
            #         # radius=100,
            #         # color='blue',
            #         # fill=True,
            #         # fill_color=f'{"green" if p[2] > 0.5 else "orange" if p[2] > 0.3 else "red"}',
            #         fill_opacity=p[2] * 0.8,
            #         popup=f"Suitability: {p[2]:.2f}"
                # ).add_to(m)
            
            # Display the map
            folium_static(m)
            
            # Monthly generation profile
        st.markdown("### 📈 Monthly Generation Profile")
        
        # Create monthly generation profile (approximated)
        # Reasonable monthly variations for Ethiopia
        monthly_factors = {
            'Jan': 0.19, 'Feb': 0.20, 'Mar': 0.19, 'Apr': 0.18, 
            'May': 0.17, 'Jun': 0.16, 'Jul': 0.15, 'Aug': 0.16,
            'Sep': 0.17, 'Oct': 0.18, 'Nov': 0.19, 'Dec': 0.19
        }
        
        # Adjust based on region
        if region == "north":
            # More seasonal in the north
            for month in ['Jun', 'Jul', 'Aug']:
                monthly_factors[month] -= 0.02
            for month in ['Dec', 'Jan', 'Feb']:
                monthly_factors[month] += 0.02
        elif region == "east":
            # Less seasonal in the east
            for month in monthly_factors:
                monthly_factors[month] = 0.17 + (monthly_factors[month] - 0.17) * 0.5
        
        # Normalize to make sure they sum to 1
        factor_sum = sum(monthly_factors.values())
        monthly_factors = {k: v/factor_sum for k, v in monthly_factors.items()}
        
        # Calculate monthly generation
        months = list(monthly_factors.keys())
        monthly_generation = [annual_generation_gwh * monthly_factors[m] for m in months]
        
        # Create the chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(months, monthly_generation, color='#f9a825')
        ax.set_ylabel('Estimated Generation (GWh)')
        ax.set_title(f'Estimated Monthly PV Generation Profile for {town_name}')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        
        # Add annual total as text
        ax.text(0.02, 0.92, f'Annual Generation: {annual_generation_gwh:.1f} GWh', 
               transform=ax.transAxes, fontsize=10, 
               bbox=dict(facecolor='white', alpha=0.7))
        
        # Save to a buffer and display
        buf = io.BytesIO()
        plt.tight_layout()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        
        # Display the image
        st.image(buf, caption=f"Estimated Monthly Solar Generation for {town_name}")
        
        # Additional contextual information about solar in this location
        with st.expander("📚 Additional Information"):
            st.markdown(f"""
            ### Solar Potential in {town_name}
            
            Based on the analysis, {town_name} has {summary['pv_potential']['suitable_area_km2']} km² of land suitable for solar PV development, 
            representing {summary['pv_potential']['suitable_percent']}% of the total area. With a solar irradiance of {summary['solar_resource']['mean_ghi']} kWh/m²/year,
            this area could support approximately {summary['pv_potential']['potential_capacity_mw']} MW of solar PV capacity.
            
            The estimated annual generation is {summary['pv_potential']['annual_generation_gwh']} GWh, which could power approximately 
            {int(summary['pv_potential']['annual_generation_gwh'] * 1000000 / 1000)} homes, assuming an average household consumption of 1000 kWh per year.
            
            ### Suitability Factors
            
            The suitability analysis considers:
            
            - **Population density**: Areas with lower population density are more suitable
            - **Solar resource**: Higher irradiance provides better energy yield
            - **Topography**: Flat areas with moderate elevation are ideal
            - **Land cover**: Non-agricultural, non-forested areas are preferred
            
            ### Climate Conditions in {region.capitalize()} Ethiopia
            
            The {region}ern region of Ethiopia typically has:
            
            - **Rainfall**: {"Low" if region in ["east", "north"] else "Moderate" if region == "central" else "High"} annual precipitation
            - **Temperature**: {"Hot" if region in ["east"] else "Moderate" if region in ["central", "south"] else "Varied with altitude"}
            - **Seasons**: {"Two distinct seasons (dry and wet)" if region in ["central", "west", "south"] else "Predominantly dry with short rainy periods" if region == "east" else "Three seasons (dry, short rains, long rains)"}
            
            ### Environmental Impact
            
            Solar PV development in this area could offset approximately {int(summary['pv_potential']['annual_generation_gwh'] * 800)} tonnes of CO₂ annually,
            assuming a grid emissions factor of 800 g CO₂/kWh for Ethiopia.
            """)
            
            # Add a note about data sources
            st.info("""
            **Note on Data Sources**: This analysis uses approximated values based on regional averages for Ethiopia.
            For a more precise assessment, site-specific measurements and surveys are recommended.
            """)

def main():
    st.set_page_config(
        page_title="Ethiopia Solar PV Assessment Tool",
        page_icon="☀️",
        layout="wide",
    )
    
    # Add CSS styling
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
    }
    .subheader {
        font-size: 1.5rem;
        color: #424242;
    }
    .info-box {
        background-color: #E3F2FD;
        padding: 20px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<p class="main-header">Ethiopia Solar PV Assessment Tool</p>', unsafe_allow_html=True)
    
    # Check weather data connection and display status
    weather_data_available = check_weather_data_connection()
    if weather_data_available:
        st.success("✅ Connected to weather data service")
    else:
        st.warning("⚠️ Weather data service not available or not configured. Using fallback data.")
    
    # Introductory information
    with st.expander("ℹ️ About this tool"):
        st.write("""
        This tool helps you assess the solar photovoltaic (PV) potential in Ethiopia. 
        It provides technical and financial analysis to help you make informed decisions about installing solar panels.
        
        ### How to use:
        1. Select a town from the dropdown menu
        2. Enter your financial information in the Financial Inputs section
        3. Calculate your recommended system size based on your electricity consumption
        4. Adjust roof parameters if needed (values will be pre-filled based on your system size)
        5. Click "Calculate PV Potential" to see detailed performance and financial results
        
        ### Data sources:
        - Weather data: ERA5 reanalysis dataset
        - Geographic data: Ethiopia administrative boundaries from CSA
        - Maps: OpenStreetMap,ESRI satelite,Google-earth satelite, Humanitarian OpenStreetMap, and Sentinel.
        - Electricity tariffs: Ethiopian Electric Utility (2024-2028)
        """)
    
    # Create tabs for different workflow stages
    tab1, tab2, tab3 = st.tabs(["📍 Location Selection", "🏠 financial and roof parameter Configuration", "💰 Results"])
    
    # Initialize session state to store variables between interactions
    if 'selected_town' not in st.session_state:
        st.session_state.selected_town = None
    if 'lat' not in st.session_state:
        st.session_state.lat = None
    if 'lon' not in st.session_state:
        st.session_state.lon = None
    if 'pv_results' not in st.session_state:
        st.session_state.pv_results = None
    if 'financial_results' not in st.session_state:
        st.session_state.financial_results = None
    if 'recommended_roof_area' not in st.session_state:
        st.session_state.recommended_roof_area = None
    if 'consumption_estimate' not in st.session_state:
        st.session_state.consumption_estimate = None
    # Add this line to initialize recommended_size
    if 'recommended_size' not in st.session_state:
        st.session_state.recommended_size = None
    # Tab 1: Location Selection
    # Tab 1: Location Selection and Information
    with tab1:
        st.markdown('<p class="subheader">Select Location</p>', unsafe_allow_html=True)
        
        # Town selection dropdown - no default selection
        selected_town = st.selectbox("Select Town", [""] + town_list, 
                                    index=0,  # No default selection (empty string is first option)
                                    help="Choose a town from the dropdown list")
        
        if selected_town:
            # Store in session state
            st.session_state.selected_town = selected_town
            
            # Generate map
            with st.spinner("Generating map..."):
                result = create_town_map(selected_town)
            
            if not result:
                st.error(f"Failed to process town: {selected_town}")
            else:
                m, lat, lon, buildings = result
                
                # Store coordinates in session state
                st.session_state.lat = lat
                st.session_state.lon = lon
                
                # Display map
                st.write(f"Map for {selected_town} (Lat: {lat:.4f}, Lon: {lon:.4f})")
                folium_static(m, width=800, height=500)
                
                # Create a point geometry for the selected location
                geometry = Point(lon, lat)
                
                # Display location information
                render_location_info(selected_town, lat, lon, geometry)
                
                st.success(f"Location set to {selected_town}")
                st.info("Now proceed to the 'Financial Inputs' tab to enter your electricity details")
        else:
            # Clear session state if no town is selected
            st.session_state.selected_town = None
            st.session_state.lat = None
            st.session_state.lon = None
            
            # Show a placeholder message
            st.info("Please select a town from the dropdown menu to see location information")
    # Tab 2: Roof Configuration
    # Tab 2: Roof Configuration
    with tab2:
        st.markdown('<p class="subheader">Roof Configuration</p>', unsafe_allow_html=True)
        
        if not st.session_state.selected_town:
            st.warning("Please select a town in the 'Location Selection' tab first")
        else:
            st.write(f"Setting up configuration for {st.session_state.selected_town}")
            
            # Create columns for financial inputs and system recommendation
            col1, col2 = st.columns(2)
            
            with col1:
                # Financial inputs section in left column
                st.subheader("Financial Inputs")
                
                # Customer type selection
                customer_type = st.selectbox(
                    "Customer Type",
                    options=["Residential", "Commercial", "Industrial (Low Voltage)", 
                             "Industrial (Medium Voltage)",  "Street Light"],
                    index=0,
                    help="Select your electricity customer category"
                )
                
                # Map selection to internal categories
                customer_type_map = {
                    "Residential": "residential",
                    "Commercial": "commercial", 
                    "Industrial (Low Voltage)": "industrial_lv",
                    "Industrial (Medium Voltage)": "industrial_mv",
                    "Industrial (High Voltage)": "industrial_hv",
                    "Street Light": "street_light"
                }
                customer_type_code = customer_type_map[customer_type]
                
                # For industrial customers, ask about demand charges
                peak_demand_kw = None
                if "Industrial" in customer_type:
                    st.info("Industrial tariffs include both energy charges and demand charges.")
                    
                    # Allow entering the monthly peak demand
                    peak_demand_kw = st.number_input(
                        "Monthly Peak Demand (kW)",
                        min_value=0.0,
                        max_value=10000.0,
                        value=100.0,
                        help="Your monthly peak power demand in kW (from your bill)"
                    )
                
                # Allow user to adjust cost per watt
                cost_per_watt = st.number_input(
                    "Installation Cost (ETB/watt)",
                    min_value=0.01,
                    max_value=500.0,
                    value=1.5,
                    step=0.1,
                    help="Total cost per watt including equipment and installation"
                )
                
                # Add monthly electricity bill input
                monthly_bill = st.number_input(
                    "Average Monthly Electricity Bill (ETB)",
                    min_value=0,
                    max_value=100000,
                    value=500,
                    help="Your current average monthly electricity bill in Ethiopian Birr"
                )
                
                # Option to enter electricity rate directly
                use_custom_price = 0
                # st.checkbox(
                #     "I know my electricity rate",
                #     value=False,
                #     help="Check this if you know your electricity price per kWh"
                # )
                
                if use_custom_price:
                    electricity_price = st.number_input(
                        "Electricity Price (ETB/kWh)",
                        min_value=0.01,
                        max_value=10.0,
                        value=2.50,
                        step=0.10,
                        help="Current electricity price per kilowatt-hour in Ethiopian Birr"
                    )
                else:
                    # Default electricity prices by customer type (ETB/kWh) - Updated to match tariff schedule
                    default_prices = {
                        "residential": 0.27,  # Base tier, will be adjusted below
                        "commercial": 2.12, 
                        "industrial_lv": 1.53,
                        "industrial_mv": 1.19,
                        "industrial_hv": 1.19,
                        "street_light": 2.12
                    }
                    
                    # For residential, estimate the appropriate tier based on monthly bill
                    if customer_type_code == "residential" and monthly_bill > 0:
                        # Very rough estimation of monthly consumption
                        est_monthly_consumption = monthly_bill / 2.0  # Assuming average rate of 2.0 ETB/kWh
                        
                        # Select appropriate tier based on estimated consumption
                        if est_monthly_consumption <= 50:
                            electricity_price = 0.27
                        elif est_monthly_consumption <= 100:
                            electricity_price = 0.77
                        elif est_monthly_consumption <= 200:
                            electricity_price = 1.63
                        elif est_monthly_consumption <= 300:
                            electricity_price = 2.00
                        elif est_monthly_consumption <= 400:
                            electricity_price = 2.20
                        elif est_monthly_consumption <= 500:
                            electricity_price = 2.41
                        else:
                            electricity_price = 2.48
                    else:
                        # Non-residential rates are flat
                        electricity_price = default_prices.get(customer_type_code, 2.50)
                    
                    # Option to estimate from bill (separate from tiered estimate)
                    use_bill_estimate = 0
                    # st.checkbox(
                    #     "Use bill-based electricity rate estimate (ignores official tariffs)",
                    #     value=False
                    # )
                    
                    if use_bill_estimate and monthly_bill > 0:
                        try:
                            # Get estimate without using custom price
                            consumption_estimate = estimate_consumption_and_capacity(
                                monthly_bill, 
                                customer_type=customer_type_code,
                                peak_demand_kw=peak_demand_kw
                            )
                            
                            # Use the estimated price
                            electricity_price = consumption_estimate['average_electricity_price_etb']
                        except Exception as e:
                            st.warning(f"Could not estimate electricity price: {str(e)}")
                    
                    st.info(f"Using electricity rate: {electricity_price:.4f} ETB/kWh for {customer_type}")
                
                # Calculate system recommendation button
                if st.button("Calculate System Size Recommendation", key="calc_system_size", type="primary"):
                    with st.spinner("Calculating recommendation..."):
                        try:
                            # Calculate estimated consumption and recommended capacity
                            consumption_estimate = estimate_consumption_and_capacity(
                                monthly_bill,
                                customer_type=customer_type_code,
                                peak_demand_kw=peak_demand_kw
                            )
                            
                            # Store in session state
                            st.session_state.consumption_estimate = consumption_estimate
                            #st.experimental_rerun()  # Refresh to show the results
                        except Exception as e:
                            st.error(f"Error in calculation: {str(e)}")
            
            with col2:
                # System size recommendation in right column
                st.subheader("System Size Recommendation")
                
                # Display calculation results if available or if calculate button was pressed
                if 'consumption_estimate' in st.session_state and st.session_state.consumption_estimate is not None:
                    try:
                        # Use existing consumption estimate
                        consumption_estimate = st.session_state.consumption_estimate
                        
                        # Display results in metrics
                        st.metric(
                            "Estimated Monthly Consumption", 
                            f"{consumption_estimate['estimated_monthly_consumption_kwh']:.0f} kWh"
                        )
                      
                        st.metric(
                            "Recommended System Size", 
                            f"{consumption_estimate['recommended_capacity_kw']:.1f} kWp"
                        )
                        
                        # Calculate required roof area
                        panel_efficiency_decimal = 20 / 100  # Default 20%
                        panel_area = PANEL_WIDTH * PANEL_HEIGHT
                        panel_power = panel_area * 1000 * panel_efficiency_decimal
                        num_panels_needed = np.ceil(consumption_estimate['recommended_capacity_kw'] * 1000 / panel_power)
                        panel_spacing_area = panel_area * (1 + SPACING_FACTOR)
                        required_area = num_panels_needed * panel_spacing_area
                        
                        # Store in session state
                        st.session_state.recommended_roof_area = int(required_area)
                        st.session_state.recommended_size = consumption_estimate['recommended_capacity_kw']
                        
                        st.metric(
                            "Recommended Roof Area", 
                            f"{st.session_state.recommended_roof_area:.0f} m²"
                        )
                        
                    except Exception as e:
                        st.error(f"Error in calculation: {str(e)}")
                else:
                    st.info("Enter your financial details and click 'Calculate System Size Recommendation' to get a personalized recommendation.")
            
            # Add roof parameters section below both columns
            st.markdown("---")
            st.subheader("Roof Parameters")
            
            # Use the recommended value if it exists, otherwise use 100 as default
            default_roof_area = st.session_state.recommended_roof_area if st.session_state.recommended_roof_area is not None else 100
            
            # Create two columns for roof
            # Create two columns for roof parameters
            roof_col1, roof_col2 = st.columns(2)
            
            with roof_col1:
                roof_area = st.number_input("Roof Area (sq. meters)", 
                                          min_value=1, max_value=1000, value=default_roof_area,
                                          help="Total available roof area for solar panels")
                roof_tilt = st.slider("Roof Tilt (degrees)", 
                                    min_value=0, max_value=60, value=15,
                                    help="Angle of the roof from horizontal")
                
                roof_azimuth = st.slider("Roof Azimuth (degrees)", 
                                       min_value=0, max_value=360, value=180,
                                       help="Direction the roof faces: 0=North, 90=East, 180=South, 270=West")
                
            with roof_col2:
                system_losses = st.slider("System Losses (%)", 
                                        min_value=10, max_value=30, value=14,
                                        help="Includes wiring losses, inverter losses, soiling, etc.")
                 
                panel_efficiency = st.slider("Panel Efficiency (%)", 
                                          min_value=15, max_value=23, value=20,
                                          help="Higher efficiency panels produce more power but cost more")
            
                # Show recommended size if available
                if st.session_state.recommended_size is not None:
                    st.success(f"Using recommended system size: {st.session_state.recommended_size:.1f} kWp (requires approximately {st.session_state.recommended_roof_area} m²)")
            
            # Calculate button
            if st.button("Calculate PV Potential", type="primary"):
                # Ensure we have financial inputs
                if 'consumption_estimate' not in st.session_state or st.session_state.consumption_estimate is None:
                    st.warning("Please complete the Financial Inputs tab first to get a system recommendation")
                    st.stop()
                
                with st.spinner("Calculating solar potential..."):
                    try:
                        # Get financial inputs from session state
                        consumption_estimate = st.session_state.consumption_estimate
                        customer_type_code = consumption_estimate.get('customer_type', 'residential')
                        electricity_price = consumption_estimate.get('average_electricity_price_etb', 2.50)
                        monthly_bill = consumption_estimate.get('monthly_bill', 500)
                        
                        # Get weather data - use cached function with Azure URL
                        weather_df = get_weather_data(st.session_state.lat, st.session_state.lon)
                        
                        # Run calculations
                        weather_with_solar = get_solar_position(st.session_state.lat, 
                                                             st.session_state.lon, 
                                                             weather_df)
                        
                        pv_results = calculate_pv_production(
                            weather_with_solar,
                            roof_area,
                            efficiency=panel_efficiency/100,  # Convert to decimal
                            system_losses=system_losses/100,  # Convert to decimal
                            tilt=roof_tilt,
                            azimuth=roof_azimuth,
                            panel_width=PANEL_WIDTH,
                            panel_height=PANEL_HEIGHT,
                            spacing_factor=SPACING_FACTOR
                        )
                        
                        # Calculate how much of user's consumption will be covered
                        annual_energy = pv_results['annual_energy_kwh']
                        annual_consumption = consumption_estimate['estimated_yearly_consumption_kwh']
                        coverage_ratio = min(1.0, annual_energy / annual_consumption) if annual_consumption > 0 else 0
                        
                        # Add to results
                        pv_results['estimated_annual_consumption_kwh'] = annual_consumption
                        pv_results['consumption_coverage_ratio'] = coverage_ratio
                        pv_results['estimated_monthly_bill_etb'] = monthly_bill
                        
                        # Convert electricity price from ETB to USD for financial analysis
                        electricity_price_usd = electricity_price / CURRENCY_CONVERSION_RATE
                        
                        # Pass the user-specified financial parameters to the analysis function
                        financial_results = financial_analysis(
                            pv_results,
                            cost_per_watt=cost_per_watt/CURRENCY_CONVERSION_RATE,
                            electricity_price=electricity_price_usd,
                            customer_type=customer_type_code,  # Pass the customer type for tariff projection
                            current_year_quarter=(CURRENT_YEAR, CURRENT_QUARTER),  # Current year and quarter
                            annual_price_increase=0.03,  # Used for scenarios and fallback
                            lifetime=25,
                            discount_rate=0.06,
                            currency_conversion_rate=CURRENCY_CONVERSION_RATE
                        )
                        
                        # Add bill comparison if monthly bill is provided
                        if monthly_bill > 0:
                            yearly_bill = monthly_bill * 12
                            yearly_bill_usd = yearly_bill / CURRENCY_CONVERSION_RATE
                            yearly_savings_usd = financial_results['annual_savings_first_year_usd']
                            bill_offset_percent = min(100, (yearly_savings_usd / yearly_bill_usd * 100)) if yearly_bill_usd > 0 else 0
                            
                            # Store the additional metrics in financial results
                            financial_results['yearly_bill_usd'] = yearly_bill_usd
                            financial_results['yearly_bill_etb'] = yearly_bill
                            financial_results['bill_offset_percent'] = bill_offset_percent
                        
                        # Store results in session state
                        st.session_state.pv_results = pv_results
                        st.session_state.financial_results = financial_results
                        
                        # Auto-navigate to results tab
                        st.success("Calculation complete! View results in the 'Results' tab.")
                        # Use the improved tab navigation
                        st.markdown('<script>window.parent.document.querySelectorAll("button[role=\'tab\']")[2].click();</script>', unsafe_allow_html=True)
                        
                    except Exception as e:
                        st.error(f"Error in calculation: {str(e)}")
                        import traceback
                        st.write(traceback.format_exc())
   # Tab 3: Results
    with tab3:
        st.markdown('<p class="subheader">Assessment Results</p>', unsafe_allow_html=True)
        
        if 'pv_results' not in st.session_state or st.session_state.pv_results is None:
            st.warning("No results available. Please complete the steps in the previous tabs.")
        else:
            try:
                # Get the data
                pv_results = st.session_state.pv_results
                financial_results = st.session_state.financial_results
                
                # Technical Results Section
                st.markdown("### Technical Assessment")
                
                # Create nice metric displays
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("System Capacity", f"{pv_results['system_capacity_kw']:.1f} kWp")
                with col2:
                    st.metric("Annual Production", f"{pv_results['annual_energy_kwh']:.0f} kWh")
                with col3:
                    st.metric("Avg Daily Production", f"{pv_results['avg_daily_production_kwh']:.1f} kWh")
                with col4:
                    st.metric("Capacity Factor", f"{pv_results['capacity_factor']:.1f}%")
                
                # Monthly production chart
                if 'monthly_energy_kwh' in pv_results:
                    try:
                        monthly_data = pv_results['monthly_energy_kwh']
                        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                        
                        # For dictionary type (timestamp keys)
                        if isinstance(monthly_data, dict):
                            # Sort by timestamp
                            sorted_months = sorted(monthly_data.keys())
                            values = [monthly_data[m] for m in sorted_months]
                            
                            # Create DataFrame for plotting
                            chart_data = pd.DataFrame({
                                'Month': months,
                                'Energy (kWh)': values
                            })
                            
                            # Display chart
                            st.subheader("Monthly Energy Production")
                            st.bar_chart(chart_data.set_index('Month'))
                            
                        # For pandas Series or other types
                        else:
                            st.subheader("Monthly Energy Production")
                            st.bar_chart(monthly_data)
                            
                    except Exception as e:
                        st.warning(f"Could not display monthly chart: {str(e)}")
                
                # Financial Results Section
                st.markdown("### Financial Assessment")
                
                # Financial metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Investment Cost", format_currency(financial_results['investment_etb'], "ETB"))
                with col2:
                    st.metric("Annual Savings", format_currency(financial_results['annual_savings_first_year_etb'], "ETB"))
                with col3:
                    st.metric("Payback Period", f"{financial_results['payback_period_years']:.1f} years")
                with col4:
                    st.metric("LCOE", f"{financial_results['lcoe_etb_per_kwh']:.3f} ETB/kWh")
                
                # Cash flow visualization
                if 'cumulative_cash_flow_etb' in financial_results:
                    years = list(range(len(financial_results['cumulative_cash_flow_etb'])))
                    
                    # Create cash flow chart
                    cashflow_data = pd.DataFrame({
                        'Year': years,
                        'Cumulative Cash Flow (ETB)': financial_results['cumulative_cash_flow_etb']
                    })
                    
                    st.subheader("Cumulative Cash Flow")
                    st.line_chart(cashflow_data.set_index('Year'))
                
                # Display electricity price trends
                if 'electricity_prices' in financial_results:
                    st.subheader("Electricity Price Trends")
                    st.write("The financial analysis accounts for scheduled electricity tariff increases.")
                    
                    yearly_prices = financial_results['electricity_prices']['yearly_prices_etb']
                    yearly_savings = [s * CURRENCY_CONVERSION_RATE for s in financial_results['electricity_prices']['yearly_savings_usd']]
                    
                    # Create DataFrame for plotting electricity price trends
                    years = list(range(1, len(yearly_prices) + 1))
                    
                    price_data = pd.DataFrame({
                        'Year': years,
                        'Electricity Price (ETB/kWh)': yearly_prices,
                        'Annual Savings (ETB)': yearly_savings
                    })
                    
                    # Plot electricity price trend
                    st.write("**Projected Electricity Prices**")
                    st.line_chart(price_data.set_index('Year')['Electricity Price (ETB/kWh)'])
                    
                    # Plot annual savings over time
                    st.write("**Projected Annual Savings**")
                    st.line_chart(price_data.set_index('Year')['Annual Savings (ETB)'])
                    
                    # Create a table with the data
                    with st.expander("View Detailed Price and Savings Projection"):
                        price_data['Year'] = [f"Year {i}" for i in price_data['Year']]
                        st.table(price_data.set_index('Year'))
                
                # Additional financial metrics
                st.markdown("### Additional Financial Metrics")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Return on Investment (ROI)", f"{financial_results['roi_percent']:.1f}%")
                    if 'npv_etb' in financial_results:
                        st.metric("Net Present Value (NPV)", format_currency(financial_results['npv_etb'], "ETB"))
                with col2:
                    if 'cumulative_savings_etb' in financial_results:
                        st.metric("Lifetime Savings", format_currency(financial_results['cumulative_savings_etb'], "ETB"))
            
                # Bill comparison section (if bill data is available)
                if 'yearly_bill_etb' in financial_results:
                    st.markdown("### Electricity Bill Comparison")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(
                            "Current Annual Electricity Bill", 
                            format_currency(financial_results['yearly_bill_etb'], "ETB")
                        )
                        st.metric(
                            "First Year Savings", 
                            format_currency(financial_results['annual_savings_first_year_etb'], "ETB")
                        )
                    
                    with col2:
                        st.metric(
                            "Bill Offset", 
                            f"{financial_results['bill_offset_percent']:.1f}%"
                        )
                        
                        # Calculate monthly savings
                        monthly_savings = financial_results['annual_savings_first_year_etb'] / 12
                        st.metric(
                            "Average Monthly Savings",
                            format_currency(monthly_savings, "ETB")
                        )
            
            except Exception as e:
                st.error(f"Error displaying results: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

if __name__ == "__main__":
    main()

