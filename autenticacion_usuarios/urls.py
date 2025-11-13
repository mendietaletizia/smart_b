from django.urls import path
from . import views
from . import notificaciones_views

app_name = 'autenticacion_usuarios'

urlpatterns = [
    # CU1: Iniciar Sesión
    path('login/', views.LoginView.as_view(), name='login'),
    
    # CU2: Cerrar Sesión
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # CU3: Registrar Cuenta del Cliente
    path('register/', views.RegisterView.as_view(), name='register'),
    
    # Vista auxiliar para verificar sesión
    path('check-session/', views.CheckSessionView.as_view(), name='check_session'),
    
    # Gestión de Clientes (CRUD)
    path('clientes/', views.ClientesListView.as_view(), name='clientes_list'),
    path('clientes/<int:cliente_id>/', views.ClienteDetailView.as_view(), name='cliente_detail'),
    path('clientes/<int:cliente_id>/ventas/', views.ClienteVentasView.as_view(), name='cliente_ventas'),
    
    # Notificaciones
    path('notificaciones/', notificaciones_views.NotificacionesView.as_view(), name='notificaciones'),
    path('notificaciones/<int:notificacion_id>/', notificaciones_views.NotificacionDetailView.as_view(), name='notificacion_detail'),
    path('notificaciones/marcar-todas-leidas/', notificaciones_views.MarcarTodasLeidasView.as_view(), name='marcar_todas_leidas'),
]

