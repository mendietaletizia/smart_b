import json
import logging
from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
from .models import Notificacion, Usuario, Rol
from productos.models import Producto, Stock
from ventas_carrito.models import Venta

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class NotificacionesView(View):
    """Obtener y crear notificaciones"""
    
    def get(self, request):
        """Obtener notificaciones del usuario actual"""
        try:
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            # Obtener usuario de la sesión
            user_id = request.session.get('user_id')
            if not user_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Usuario no encontrado en sesión'
                }, status=401)
            
            try:
                usuario = Usuario.objects.get(id=user_id)
            except Usuario.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Usuario no encontrado'
                }, status=404)
            
            # Parámetros de filtro
            tipo = request.GET.get('tipo', None)
            leida = request.GET.get('leida', None)
            prioridad = request.GET.get('prioridad', None)
            limite = int(request.GET.get('limite', 50))
            
            # Obtener notificaciones del usuario
            notificaciones = Notificacion.objects.filter(id_usuario=usuario)
            
            # Aplicar filtros
            if tipo:
                notificaciones = notificaciones.filter(tipo=tipo)
            if leida is not None:
                leida_bool = leida.lower() == 'true'
                notificaciones = notificaciones.filter(leido=leida_bool)
            if prioridad:
                notificaciones = notificaciones.filter(prioridad=prioridad)
            
            # Ordenar por fecha más reciente y limitar
            notificaciones = notificaciones.order_by('-fecha_envio')[:limite]
            
            # Serializar notificaciones
            notificaciones_data = []
            for notif in notificaciones:
                notificaciones_data.append({
                    'id': notif.id_notificacion,
                    'titulo': notif.titulo,
                    'mensaje': notif.mensaje,
                    'tipo': notif.tipo,
                    'prioridad': notif.prioridad,
                    'fecha': notif.fecha_envio.isoformat() if notif.fecha_envio else None,
                    'leida': notif.leido,
                    'usuario': {
                        'id': usuario.id,
                        'nombre': usuario.nombre
                    }
                })
            
            # Contar no leídas
            no_leidas = Notificacion.objects.filter(id_usuario=usuario, leido=False).count()
            
            return JsonResponse({
                'success': True,
                'notificaciones': notificaciones_data,
                'total': len(notificaciones_data),
                'no_leidas': no_leidas
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en NotificacionesView GET: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al obtener notificaciones: {str(e)}'
            }, status=500)
    
    def post(self, request):
        """Crear nueva notificación (solo para administradores)"""
        try:
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            # Verificar que sea administrador
            user_id = request.session.get('user_id')
            if user_id:
                try:
                    usuario = Usuario.objects.get(id=user_id)
                    es_admin = usuario.id_rol and usuario.id_rol.nombre.lower() in ['administrador', 'admin']
                    if not es_admin:
                        return JsonResponse({
                            'success': False,
                            'message': 'Solo los administradores pueden crear notificaciones'
                        }, status=403)
                except Usuario.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Usuario no encontrado'
                    }, status=404)
            
            data = json.loads(request.body)
            
            titulo = data.get('titulo')
            mensaje = data.get('mensaje')
            tipo = data.get('tipo', 'info')
            prioridad = data.get('prioridad', 'normal')
            destinatario = data.get('destinatario', 'todos')  # todos, clientes, administradores, especifico
            usuario_especifico_id = data.get('usuario_id', None)
            
            if not titulo or not mensaje:
                return JsonResponse({
                    'success': False,
                    'message': 'Título y mensaje son requeridos'
                }, status=400)
            
            # Determinar destinatarios
            usuarios_destinatarios = []
            
            if destinatario == 'especifico' and usuario_especifico_id:
                try:
                    usuario_esp = Usuario.objects.get(id=usuario_especifico_id)
                    usuarios_destinatarios.append(usuario_esp)
                except Usuario.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Usuario específico no encontrado'
                    }, status=404)
            elif destinatario == 'clientes':
                try:
                    rol_cliente = Rol.objects.filter(nombre__icontains='cliente').first()
                    if rol_cliente:
                        usuarios_destinatarios = list(Usuario.objects.filter(id_rol=rol_cliente))
                    else:
                        usuarios_destinatarios = list(Usuario.objects.exclude(id_rol__nombre__icontains='admin'))
                except:
                    usuarios_destinatarios = list(Usuario.objects.all())
            elif destinatario == 'administradores':
                try:
                    rol_admin = Rol.objects.filter(nombre__icontains='admin').first()
                    if rol_admin:
                        usuarios_destinatarios = list(Usuario.objects.filter(id_rol=rol_admin))
                except:
                    usuarios_destinatarios = []
            else:  # todos
                usuarios_destinatarios = list(Usuario.objects.all())
            
            # Crear notificaciones para cada destinatario
            notificaciones_creadas = []
            for usuario_dest in usuarios_destinatarios:
                notificacion = Notificacion.objects.create(
                    titulo=titulo,
                    mensaje=mensaje,
                    tipo=tipo,
                    prioridad=prioridad,
                    id_usuario=usuario_dest
                )
                notificaciones_creadas.append(notificacion.id_notificacion)
            
            return JsonResponse({
                'success': True,
                'message': f'Notificación enviada a {len(notificaciones_creadas)} usuario(s)',
                'notificaciones_creadas': len(notificaciones_creadas)
            }, status=201)
            
        except Exception as e:
            logger.error(f"Error en NotificacionesView POST: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al crear notificación: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class NotificacionDetailView(View):
    """Gestionar una notificación específica"""
    
    def patch(self, request, notificacion_id):
        """Marcar notificación como leída/no leída"""
        try:
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            user_id = request.session.get('user_id')
            if not user_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Usuario no encontrado en sesión'
                }, status=401)
            
            try:
                notificacion = Notificacion.objects.get(
                    id_notificacion=notificacion_id,
                    id_usuario_id=user_id
                )
            except Notificacion.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Notificación no encontrada'
                }, status=404)
            
            data = json.loads(request.body)
            leida = data.get('leida', True)
            
            notificacion.leido = leida
            notificacion.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Notificación actualizada',
                'notificacion': {
                    'id': notificacion.id_notificacion,
                    'leida': notificacion.leido
                }
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en NotificacionDetailView PATCH: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al actualizar notificación: {str(e)}'
            }, status=500)
    
    def delete(self, request, notificacion_id):
        """Eliminar notificación"""
        try:
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            user_id = request.session.get('user_id')
            if not user_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Usuario no encontrado en sesión'
                }, status=401)
            
            try:
                notificacion = Notificacion.objects.get(
                    id_notificacion=notificacion_id,
                    id_usuario_id=user_id
                )
            except Notificacion.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Notificación no encontrada'
                }, status=404)
            
            notificacion.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Notificación eliminada'
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en NotificacionDetailView DELETE: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al eliminar notificación: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class MarcarTodasLeidasView(View):
    """Marcar todas las notificaciones del usuario como leídas"""
    
    def post(self, request):
        try:
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión'
                }, status=401)
            
            user_id = request.session.get('user_id')
            if not user_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Usuario no encontrado en sesión'
                }, status=401)
            
            actualizadas = Notificacion.objects.filter(
                id_usuario_id=user_id,
                leido=False
            ).update(leido=True)
            
            return JsonResponse({
                'success': True,
                'message': f'{actualizadas} notificaciones marcadas como leídas',
                'actualizadas': actualizadas
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en MarcarTodasLeidasView: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al marcar notificaciones: {str(e)}'
            }, status=500)


def crear_notificacion_automatica(usuario, titulo, mensaje, tipo='info', prioridad='normal'):
    """Función auxiliar para crear notificaciones automáticas"""
    try:
        notificacion = Notificacion.objects.create(
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            prioridad=prioridad,
            id_usuario=usuario
        )
        return notificacion
    except Exception as e:
        logger.error(f"Error creando notificación automática: {str(e)}")
        return None


def notificar_stock_bajo():
    """Crear notificaciones para productos con stock bajo (solo para administradores)"""
    try:
        # Obtener productos con stock bajo (menos de 10 unidades)
        productos_stock_bajo = Producto.objects.filter(
            stock__cantidad__lt=10,
            stock__cantidad__gt=0
        ).select_related('stock')[:20]  # Limitar a 20 para no saturar
        
        if not productos_stock_bajo.exists():
            return
        
        # Obtener administradores
        try:
            rol_admin = Rol.objects.filter(nombre__icontains='admin').first()
            if rol_admin:
                administradores = Usuario.objects.filter(id_rol=rol_admin)
            else:
                administradores = Usuario.objects.filter(id_rol__nombre__icontains='admin')
        except:
            return
        
        # Crear notificaciones para cada administrador
        for admin in administradores:
            productos_lista = []
            for producto in productos_stock_bajo[:5]:  # Limitar a 5 productos por notificación
                stock = producto.stock.first() if hasattr(producto, 'stock') else None
                if stock:
                    productos_lista.append(f"{producto.nombre} ({stock.cantidad} unidades)")
            
            if productos_lista:
                mensaje = f"Productos con stock bajo: {', '.join(productos_lista)}"
                if len(productos_stock_bajo) > 5:
                    mensaje += f" y {len(productos_stock_bajo) - 5} más..."
                
                crear_notificacion_automatica(
                    usuario=admin,
                    titulo="⚠️ Stock Bajo",
                    mensaje=mensaje,
                    tipo='stock',
                    prioridad='alta'
                )
        
    except Exception as e:
        logger.error(f"Error en notificar_stock_bajo: {str(e)}")


def notificar_nueva_venta(venta):
    """Crear notificación para administradores cuando hay una nueva venta"""
    try:
        # Obtener administradores
        try:
            rol_admin = Rol.objects.filter(nombre__icontains='admin').first()
            if rol_admin:
                administradores = Usuario.objects.filter(id_rol=rol_admin)
            else:
                administradores = Usuario.objects.filter(id_rol__nombre__icontains='admin')
        except:
            return
        
        mensaje = f"Nueva venta realizada por Bs. {float(venta.total):.2f}"
        # Intentar obtener el cliente/usuario de la venta
        try:
            if hasattr(venta, 'cliente') and venta.cliente:
                if hasattr(venta.cliente, 'id') and hasattr(venta.cliente.id, 'nombre'):
                    mensaje += f" - Cliente: {venta.cliente.id.nombre}"
                elif hasattr(venta.cliente, 'nombre'):
                    mensaje += f" - Cliente: {venta.cliente.nombre}"
            elif hasattr(venta, 'id_usuario') and venta.id_usuario:
                mensaje += f" - Cliente: {venta.id_usuario.nombre}"
        except:
            pass  # Si no se puede obtener el nombre del cliente, continuar sin él
        
        # Crear notificación para cada administrador
        for admin in administradores:
            crear_notificacion_automatica(
                usuario=admin,
                titulo="💰 Nueva Venta",
                mensaje=mensaje,
                tipo='venta',
                prioridad='normal'
            )
        
    except Exception as e:
        logger.error(f"Error en notificar_nueva_venta: {str(e)}")

