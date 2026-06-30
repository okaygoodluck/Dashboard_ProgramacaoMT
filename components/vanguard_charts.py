import streamlit as st
import altair as alt

def render_volume_by_responsible(df_agg):
    """Gera o gráfico de volume total por responsável."""
    st.markdown("##### Volume por Responsável")
    
    chart = alt.Chart(df_agg).mark_bar(
        cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color=alt.Gradient(
            gradient='linear', stops=[alt.GradientStop(color='#3b82f6', offset=0), alt.GradientStop(color='#60a5fa', offset=1)]
        )
    ).encode(
        x=alt.X('Responsavel', sort='-y', axis=alt.Axis(labelLimit=200, title=None, labelAngle=-45)),
        y=alt.Y('Total', title='Volume', axis=alt.Axis(format='d')),
        tooltip=['Responsavel', 'Total', 'Total Critico']
    ).properties(height=300, background='transparent').configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)

def render_delays_by_responsible(df_agg):
    """Gera o gráfico de atrasos por responsável."""
    st.markdown("##### Atrasos por Responsável")
    
    df_atraso = df_agg.sort_values('Atrasadas', ascending=False)
    chart = alt.Chart(df_atraso).mark_bar(
        color='#ff4b4b', cornerRadiusTopLeft=5, cornerRadiusTopRight=5
    ).encode(
        x=alt.X('Responsavel', sort='-y', axis=alt.Axis(labelLimit=200, title=None, labelAngle=-45)),
        y=alt.Y('Atrasadas', title='Qtd Atrasos', axis=alt.Axis(format='d')),
        tooltip=['Responsavel', 'Atrasadas', 'Total']
    ).properties(height=300, background='transparent').configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)

def render_volume_by_mesh(df_agg, col_malha):
    """Gera o gráfico de volume por malha (Top 10)."""
    st.markdown("##### Top 10 Malhas (Volume)")
    
    top_malhas = df_agg.head(10)
    chart = alt.Chart(top_malhas).mark_bar().encode(
        x=alt.X(col_malha, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
        y=alt.Y('Total', title='Volume', axis=alt.Axis(format='d')),
        tooltip=[col_malha, 'Total', '% Atraso']
    ).properties(height=300, background='transparent').configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)

def render_delays_by_mesh(df_agg, col_malha):
    """Gera o gráfico de atrasos por malha (Top 10)."""
    st.markdown("##### Top Malhas com Atraso")
    
    df_atraso = df_agg.sort_values('Atrasadas', ascending=False).head(10)
    chart = alt.Chart(df_atraso).mark_bar(color='#ff4b4b').encode(
        x=alt.X(col_malha, sort='-y', axis=alt.Axis(labelLimit=200, title=None)),
        y=alt.Y('Atrasadas', title='Qtd Atrasos', axis=alt.Axis(format='d')),
        tooltip=[col_malha, 'Atrasadas', 'Total']
    ).properties(height=300, background='transparent').configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)

def render_qty_x_weight_chart(df_plot, col_regiao):
    """Gera o gráfico de barras agrupadas Quantidade x Peso por Região."""
    
    chart = alt.Chart(df_plot).mark_bar().encode(
        x=alt.X('Peso:N', title='Peso Unitário', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('Quantidade:Q', title='Qtde Manobras', axis=alt.Axis(format='d')),
        color=alt.Color(col_regiao, title='Região', scale=alt.Scale(scheme='tableau10')),
        xOffset=alt.XOffset(col_regiao),
        tooltip=[col_regiao, 'Peso', 'Quantidade']
    ).properties(
        height=400,
        background='transparent'
    ).configure_view(
        strokeOpacity=0
    )
    st.altair_chart(chart, use_container_width=True)
