from django.urls import path
from . import views
from . import ofertas_views

app_name = 'productos'

urlpatterns = [
    path('', views.ProductoListView.as_view(), name='list_products'),
    path('admin/', views.ProductoAdminView.as_view(), name='admin_products'),
    path('upload-image/', views.UploadImageView.as_view(), name='upload_image'),
    path('categorias/', views.CategoriaListView.as_view(), name='list_categorias'),
            # Ofertas y Cupones
            path('ofertas/', ofertas_views.OfertasView.as_view(), name='ofertas'),
            path('ofertas/sugerir-ia/', ofertas_views.SugerirOfertasIAView.as_view(), name='sugerir_ofertas_ia'),
            path('cupones/', ofertas_views.CuponesView.as_view(), name='cupones'),
            path('cupones/validar/', ofertas_views.ValidarCuponView.as_view(), name='validar_cupon'),
]

