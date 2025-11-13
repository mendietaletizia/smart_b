import json
import logging
from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Q, Count, Sum, Avg
from productos.models import Oferta, CuponDescuento, Producto, Categoria, Stock
from ventas_carrito.models import Venta, DetalleVenta
from reportes_dinamicos.models import PrediccionVenta
from autenticacion_usuarios.models import Notificacion, Usuario

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class OfertasView(View):
    """Gestionar ofertas - Listar y crear"""
    
    def get(self, request):
        """Listar ofertas"""
        try:
            estado = request.GET.get('estado', None)
            activas = request.GET.get('activas', None)
            
            ofertas = Oferta.objects.all().select_related('producto', 'categoria')
            
            if estado:
                ofertas = ofertas.filter(estado=estado)
            
            if activas == 'true':
                ahora = timezone.now()
                ofertas = ofertas.filter(
                    fecha_inicio__lte=ahora,
                    fecha_fin__gte=ahora,
                    estado='activa'
                )
            
            ofertas_data = []
            for oferta in ofertas:
                try:
                    ofertas_data.append({
                        'id': oferta.id_oferta,
                        'nombre': oferta.nombre or '',
                        'descripcion': oferta.descripcion or '',
                        'producto': {
                            'id': oferta.producto.id,
                            'nombre': oferta.producto.nombre,
                            'imagen': oferta.producto.imagen or ''
                        } if oferta.producto else None,
                        'categoria': {
                            'id': oferta.categoria.id_categoria,
                            'nombre': oferta.categoria.nombre
                        } if oferta.categoria else None,
                        'descuento_porcentaje': float(oferta.descuento_porcentaje) if oferta.descuento_porcentaje else 0.0,
                        'precio_oferta': float(oferta.precio_oferta) if oferta.precio_oferta else None,
                        'fecha_inicio': oferta.fecha_inicio.isoformat() if oferta.fecha_inicio else None,
                        'fecha_fin': oferta.fecha_fin.isoformat() if oferta.fecha_fin else None,
                        'estado': oferta.estado or 'programada',
                        'imagen': oferta.imagen or '',
                        'basada_en_ia': oferta.basada_en_ia or False,
                        'razon_ia': oferta.razon_ia or '',
                        'esta_activa': oferta.esta_activa
                    })
                except Exception as e:
                    logger.warning(f"Error procesando oferta {oferta.id_oferta}: {str(e)}")
                    continue
            
            return JsonResponse({
                'success': True,
                'ofertas': ofertas_data,
                'total': len(ofertas_data)
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en OfertasView GET: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al obtener ofertas: {str(e)}'
            }, status=500)
    
    def post(self, request):
        """Crear nueva oferta"""
        try:
            # Verificar autenticación usando sesión (consistente con el resto del proyecto)
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            data = json.loads(request.body)
            
            # Validar datos requeridos
            nombre = data.get('nombre')
            if not nombre:
                return JsonResponse({
                    'success': False,
                    'message': 'El nombre de la oferta es requerido'
                }, status=400)
            
            descuento = float(data.get('descuento_porcentaje', 0))
            if descuento <= 0 or descuento > 100:
                return JsonResponse({
                    'success': False,
                    'message': 'El descuento debe estar entre 1 y 100'
                }, status=400)
            
            fecha_inicio = datetime.fromisoformat(data.get('fecha_inicio').replace('Z', '+00:00'))
            fecha_fin = datetime.fromisoformat(data.get('fecha_fin').replace('Z', '+00:00'))
            
            if fecha_fin <= fecha_inicio:
                return JsonResponse({
                    'success': False,
                    'message': 'La fecha de fin debe ser posterior a la fecha de inicio'
                }, status=400)
            
            # Crear oferta
            oferta = Oferta.objects.create(
                nombre=nombre,
                descripcion=data.get('descripcion', ''),
                producto_id=data.get('producto_id'),
                categoria_id=data.get('categoria_id'),
                descuento_porcentaje=descuento,
                precio_oferta=data.get('precio_oferta'),
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                estado=data.get('estado', 'programada'),
                imagen=data.get('imagen'),
                basada_en_ia=data.get('basada_en_ia', False),
                razon_ia=data.get('razon_ia')
            )
            
            # Enviar notificación automática a todos los clientes
            try:
                # Obtener todos los usuarios con rol de cliente (intentar diferentes variaciones del nombre)
                from autenticacion_usuarios.models import Rol
                try:
                    rol_cliente = Rol.objects.filter(
                        nombre__icontains='cliente'
                    ).first()
                    if rol_cliente:
                        clientes = Usuario.objects.filter(id_rol=rol_cliente)
                    else:
                        # Si no existe rol Cliente, obtener todos los usuarios que no son admin
                        clientes = Usuario.objects.exclude(id_rol__nombre__icontains='admin')
                except:
                    # Fallback: obtener todos los usuarios
                    clientes = Usuario.objects.all()
                
                mensaje = f"¡Nueva oferta disponible! {nombre} - {descuento}% de descuento"
                if oferta.descripcion:
                    mensaje += f". {oferta.descripcion}"
                
                # Crear notificaciones para cada cliente
                notificaciones_creadas = []
                for cliente in clientes:
                    notificacion = Notificacion.objects.create(
                        titulo=f"🎉 Nueva Oferta: {nombre}",
                        mensaje=mensaje,
                        tipo='oferta',
                        prioridad='normal',
                        id_usuario=cliente
                    )
                    notificaciones_creadas.append(notificacion.id_notificacion)
                
                logger.info(f"Notificaciones de oferta enviadas a {len(notificaciones_creadas)} clientes")
            except Exception as e:
                logger.warning(f"Error enviando notificaciones de oferta: {str(e)}")
                # No fallar la creación de la oferta si falla el envío de notificaciones
            
            return JsonResponse({
                'success': True,
                'message': f'Oferta creada exitosamente. Notificación enviada a {len(notificaciones_creadas) if "notificaciones_creadas" in locals() else 0} clientes.',
                'oferta': {
                    'id': oferta.id_oferta,
                    'nombre': oferta.nombre,
                    'estado': oferta.estado
                }
            }, status=201)
            
        except Exception as e:
            logger.error(f"Error en OfertasView POST: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al crear oferta: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class SugerirOfertasIAView(View):
    """Sugerir ofertas basadas en predicciones de IA y productos con bajo movimiento"""
    
    def get(self, request):
        """Obtener sugerencias de ofertas basadas en IA"""
        try:
            sugerencias = []
            
            # 1. Productos con bajo movimiento (pocas ventas)
            productos_bajo_movimiento = DetalleVenta.objects.values(
                'producto_id'
            ).annotate(
                total_vendido=Sum('cantidad')
            ).filter(
                total_vendido__lt=5  # Menos de 5 unidades vendidas
            ).order_by('total_vendido')[:10]
            
            for item in productos_bajo_movimiento:
                try:
                    producto = Producto.objects.get(id=item['producto_id'])
                    stock = Stock.objects.filter(producto_id=producto.id).first()
                    
                    if stock and stock.cantidad > 0:
                        sugerencias.append({
                            'tipo': 'bajo_movimiento',
                            'producto': {
                                'id': producto.id,
                                'nombre': producto.nombre,
                                'precio': float(producto.precio),
                                'imagen': producto.imagen,
                                'stock': stock.cantidad
                            },
                            'razon': f'Producto con bajo movimiento de ventas ({item["total_vendido"]} unidades vendidas)',
                            'descuento_sugerido': 15.0,  # 15% de descuento sugerido
                            'prioridad': 'alta'
                        })
                except Producto.DoesNotExist:
                    continue
            
            # 2. Productos con predicciones bajas de IA
            predicciones_bajas = PrediccionVenta.objects.filter(
                valor_predicho__lt=100,  # Predicciones de venta bajas
                fecha_prediccion__gte=timezone.now().date()
            ).order_by('valor_predicho')[:5]
            
            for pred in predicciones_bajas:
                if pred.categoria:
                    categoria = pred.categoria
                    productos_categoria = Producto.objects.filter(
                        categoria=categoria
                    )[:3]
                    
                    for producto in productos_categoria:
                        stock = Stock.objects.filter(producto_id=producto.id).first()
                        if stock and stock.cantidad > 0:
                            sugerencias.append({
                                'tipo': 'prediccion_baja',
                                'producto': {
                                    'id': producto.id,
                                    'nombre': producto.nombre,
                                    'precio': float(producto.precio),
                                    'imagen': producto.imagen,
                                    'stock': stock.cantidad
                                },
                                'categoria': {
                                    'id': categoria.id_categoria,
                                    'nombre': categoria.nombre
                                },
                                'razon': f'Categoría con predicciones bajas de ventas según IA',
                                'descuento_sugerido': 20.0,  # 20% de descuento sugerido
                                'prioridad': 'media'
                            })
            
            # 3. Ofertas basadas en fechas del año (temporadas)
            mes_actual = timezone.now().month
            ofertas_temporada = []
            
            # Ejemplos de temporadas
            if mes_actual in [11, 12, 1]:  # Navidad/Año Nuevo
                ofertas_temporada.append({
                    'tipo': 'temporada',
                    'nombre': 'Oferta de Navidad',
                    'descripcion': 'Descuentos especiales por temporada navideña',
                    'descuento_sugerido': 25.0,
                    'fecha_sugerida_inicio': timezone.now().isoformat(),
                    'fecha_sugerida_fin': (timezone.now() + timedelta(days=30)).isoformat()
                })
            elif mes_actual in [2, 3]:  # San Valentín
                ofertas_temporada.append({
                    'tipo': 'temporada',
                    'nombre': 'Oferta de San Valentín',
                    'descripcion': 'Descuentos especiales por San Valentín',
                    'descuento_sugerido': 20.0,
                    'fecha_sugerida_inicio': timezone.now().isoformat(),
                    'fecha_sugerida_fin': (timezone.now() + timedelta(days=15)).isoformat()
                })
            elif mes_actual in [5, 6]:  # Día de la Madre
                ofertas_temporada.append({
                    'tipo': 'temporada',
                    'nombre': 'Oferta Día de la Madre',
                    'descripcion': 'Descuentos especiales por el Día de la Madre',
                    'descuento_sugerido': 20.0,
                    'fecha_sugerida_inicio': timezone.now().isoformat(),
                    'fecha_sugerida_fin': (timezone.now() + timedelta(days=15)).isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'sugerencias_productos': sugerencias,
                'ofertas_temporada': ofertas_temporada,
                'total_sugerencias': len(sugerencias)
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en SugerirOfertasIAView: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al obtener sugerencias: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ValidarCuponView(View):
    """Validar un cupón de descuento para aplicar en el carrito"""
    
    def post(self, request):
        """Validar código de cupón"""
        try:
            data = json.loads(request.body)
            codigo = data.get('codigo', '').upper().strip()
            
            if not codigo:
                return JsonResponse({
                    'success': False,
                    'message': 'Código de cupón requerido'
                }, status=400)
            
            # Buscar cupón
            try:
                cupon = CuponDescuento.objects.get(codigo=codigo)
            except CuponDescuento.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Código de descuento no válido'
                }, status=404)
            
            # Validar que esté activo
            ahora = timezone.now()
            if not cupon.esta_activo:
                return JsonResponse({
                    'success': False,
                    'message': 'El cupón no está activo o ha expirado'
                }, status=400)
            
            # Validar usos disponibles
            if cupon.usos_actuales >= cupon.usos_maximos:
                return JsonResponse({
                    'success': False,
                    'message': 'El cupón ha alcanzado su límite de usos'
                }, status=400)
            
            # Obtener total del carrito si está disponible
            total_carrito = float(data.get('total_carrito', 0))
            
            # Validar monto mínimo si aplica
            if cupon.monto_minimo > 0 and total_carrito < float(cupon.monto_minimo):
                return JsonResponse({
                    'success': False,
                    'message': f'El cupón requiere un monto mínimo de Bs. {cupon.monto_minimo:.2f}'
                }, status=400)
            
            # Retornar información del cupón válido
            return JsonResponse({
                'success': True,
                'cupon': {
                    'id': cupon.id_cupon,
                    'codigo': cupon.codigo,
                    'tipo_descuento': cupon.tipo_descuento,
                    'valor_descuento': float(cupon.valor_descuento),
                    'monto_minimo': float(cupon.monto_minimo),
                    'descripcion': cupon.descripcion or ''
                },
                'message': 'Cupón válido'
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en ValidarCuponView: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al validar cupón: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class CuponesView(View):
    """Gestionar cupones de descuento"""
    
    def get(self, request):
        """Listar cupones"""
        try:
            estado = request.GET.get('estado', None)
            activos = request.GET.get('activos', None)
            
            cupones = CuponDescuento.objects.all().select_related('categoria')
            
            if estado:
                cupones = cupones.filter(estado=estado)
            
            if activos == 'true':
                ahora = timezone.now()
                cupones = cupones.filter(
                    fecha_inicio__lte=ahora,
                    fecha_fin__gte=ahora,
                    estado='activo'
                )
            
            cupones_data = []
            for cupon in cupones:
                cupones_data.append({
                    'id': cupon.id_cupon,
                    'codigo': cupon.codigo,
                    'descripcion': cupon.descripcion,
                    'tipo_descuento': cupon.tipo_descuento,
                    'valor_descuento': float(cupon.valor_descuento),
                    'monto_minimo': float(cupon.monto_minimo),
                    'fecha_inicio': cupon.fecha_inicio.isoformat(),
                    'fecha_fin': cupon.fecha_fin.isoformat(),
                    'estado': cupon.estado,
                    'usos_maximos': cupon.usos_maximos,
                    'usos_actuales': cupon.usos_actuales,
                    'aplicable_a_todos': cupon.aplicable_a_todos,
                    'categoria': {
                        'id': cupon.categoria.id_categoria,
                        'nombre': cupon.categoria.nombre
                    } if cupon.categoria else None,
                    'esta_activo': cupon.esta_activo
                })
            
            return JsonResponse({
                'success': True,
                'cupones': cupones_data,
                'total': len(cupones_data)
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en CuponesView GET: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al obtener cupones: {str(e)}'
            }, status=500)
    
    def post(self, request):
        """Crear nuevo cupón"""
        try:
            # Verificar autenticación usando sesión (consistente con el resto del proyecto)
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            data = json.loads(request.body)
            
            codigo = data.get('codigo', '').upper().strip()
            if not codigo:
                return JsonResponse({
                    'success': False,
                    'message': 'El código del cupón es requerido'
                }, status=400)
            
            # Verificar que el código no exista
            if CuponDescuento.objects.filter(codigo=codigo).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Ya existe un cupón con este código'
                }, status=400)
            
            fecha_inicio = datetime.fromisoformat(data.get('fecha_inicio').replace('Z', '+00:00'))
            fecha_fin = datetime.fromisoformat(data.get('fecha_fin').replace('Z', '+00:00'))
            
            if fecha_fin <= fecha_inicio:
                return JsonResponse({
                    'success': False,
                    'message': 'La fecha de fin debe ser posterior a la fecha de inicio'
                }, status=400)
            
            cupon = CuponDescuento.objects.create(
                codigo=codigo,
                descripcion=data.get('descripcion', ''),
                tipo_descuento=data.get('tipo_descuento', 'porcentaje'),
                valor_descuento=float(data.get('valor_descuento', 0)),
                monto_minimo=float(data.get('monto_minimo', 0)),
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                usos_maximos=int(data.get('usos_maximos', 1)),
                aplicable_a_todos=data.get('aplicable_a_todos', True),
                categoria_id=data.get('categoria_id')
            )
            
            # Enviar notificación automática a todos los clientes
            try:
                # Obtener todos los usuarios con rol de cliente (intentar diferentes variaciones del nombre)
                from autenticacion_usuarios.models import Rol
                try:
                    rol_cliente = Rol.objects.filter(
                        nombre__icontains='cliente'
                    ).first()
                    if rol_cliente:
                        clientes = Usuario.objects.filter(id_rol=rol_cliente)
                    else:
                        # Si no existe rol Cliente, obtener todos los usuarios que no son admin
                        clientes = Usuario.objects.exclude(id_rol__nombre__icontains='admin')
                except:
                    # Fallback: obtener todos los usuarios
                    clientes = Usuario.objects.all()
                
                tipo_desc = 'porcentaje' if cupon.tipo_descuento == 'porcentaje' else 'monto fijo'
                valor_desc = f"{cupon.valor_descuento}%" if cupon.tipo_descuento == 'porcentaje' else f"Bs. {cupon.valor_descuento}"
                mensaje = f"¡Nuevo cupón de descuento disponible! Código: {codigo} - {valor_desc} de descuento"
                if cupon.descripcion:
                    mensaje += f". {cupon.descripcion}"
                
                # Crear notificaciones para cada cliente
                notificaciones_creadas = []
                for cliente in clientes:
                    notificacion = Notificacion.objects.create(
                        titulo=f"🎁 Nuevo Cupón: {codigo}",
                        mensaje=mensaje,
                        tipo='cupon',
                        prioridad='normal',
                        id_usuario=cliente
                    )
                    notificaciones_creadas.append(notificacion.id_notificacion)
                
                logger.info(f"Notificaciones de cupón enviadas a {len(notificaciones_creadas)} clientes")
            except Exception as e:
                logger.warning(f"Error enviando notificaciones de cupón: {str(e)}")
                # No fallar la creación del cupón si falla el envío de notificaciones
            
            return JsonResponse({
                'success': True,
                'message': f'Cupón creado exitosamente. Notificación enviada a {len(notificaciones_creadas) if "notificaciones_creadas" in locals() else 0} clientes.',
                'cupon': {
                    'id': cupon.id_cupon,
                    'codigo': cupon.codigo,
                    'estado': cupon.estado
                }
            }, status=201)
            
        except Exception as e:
            logger.error(f"Error en CuponesView POST: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al crear cupón: {str(e)}'
            }, status=500)

