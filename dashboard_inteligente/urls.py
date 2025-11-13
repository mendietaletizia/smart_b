from django.urls import path
from . import views
from . import reportes_views

app_name = 'dashboard_inteligente'

urlpatterns = [
    path('modelo/estado/', views.EstadoModeloView.as_view(), name='estado_modelo'),
    path('modelo/entrenar/', views.EntrenarModeloView.as_view(), name='entrenar_modelo'),
    path('modelo/actualizar/', views.ActualizarModeloView.as_view(), name='actualizar_modelo'),
    path('modelo/historial/', views.HistorialEntrenamientosView.as_view(), name='historial_entrenamientos'),
    path('predicciones/generar/', views.GenerarPrediccionesView.as_view(), name='generar_predicciones'),
    path('predicciones/', views.GenerarPrediccionesView.as_view(), name='listar_predicciones'),
    # Exportar reportes
    path('dashboard-ventas/exportar/', reportes_views.ExportarDashboardVentasView.as_view(), name='exportar_dashboard'),
    path('predicciones/exportar/', reportes_views.ExportarPrediccionesView.as_view(), name='exportar_predicciones'),
]

