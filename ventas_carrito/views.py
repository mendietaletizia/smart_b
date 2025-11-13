from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.sessions.models import Session
import json
import logging

from .models import Carrito, ItemCarrito, Venta, DetalleVenta
from productos.models import Producto

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class CarritoView(View):
    """CU8 y CU9: Gestión completa del carrito de compras"""
    
    def get(self, request):
        """Obtener el carrito del usuario"""
        try:
            carrito = self._get_or_create_carrito(request)
            
            items = ItemCarrito.objects.filter(carrito=carrito).select_related('producto')
            
            data = {
                'carrito_id': carrito.id_carrito,
                'total_items': carrito.get_total_items(),
                'total_precio': float(carrito.get_total_precio()),
                'items': []
            }
            
            for item in items:
                data['items'].append({
                    'id': item.id_item,
                    'producto_id': item.producto.id,
                    'producto_nombre': item.producto.nombre,
                    'producto_imagen': item.producto.imagen,
                    'cantidad': item.cantidad,
                    'precio_unitario': float(item.precio_unitario),
                    'subtotal': float(item.get_subtotal()),
                })
            
            return JsonResponse({
                'success': True,
                'data': data
            }, status=200)
            
        except Exception as e:
            logger.error(f"Error en CarritoView.get: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al obtener carrito: {str(e)}'
            }, status=500)

    def post(self, request):
        """CU8: Añadir producto al carrito"""
        try:
            data = json.loads(request.body)
            producto_id = data.get('producto_id')
            cantidad = data.get('cantidad', 1)
            
            if not producto_id:
                return JsonResponse({
                    'success': False,
                    'message': 'ID de producto requerido'
                }, status=400)
            
            try:
                producto = Producto.objects.get(id=producto_id)
            except Producto.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Producto no encontrado'
                }, status=404)
            
            # Validar cantidad
            if cantidad <= 0:
                return JsonResponse({
                    'success': False,
                    'message': 'La cantidad debe ser mayor a 0'
                }, status=400)
            
            # Obtener o crear carrito
            carrito = self._get_or_create_carrito(request)
            
            # Validar stock disponible
            from productos.models import Stock
            stock_obj = Stock.objects.filter(producto=producto).first()
            stock_disponible = stock_obj.cantidad if stock_obj else 0
            
            # Calcular cantidad total que se intenta agregar
            cantidad_actual = 0
            item_existente = ItemCarrito.objects.filter(
                carrito=carrito,
                producto=producto
            ).first()
            if item_existente:
                cantidad_actual = item_existente.cantidad
            
            cantidad_total = cantidad_actual + cantidad
            
            if cantidad_total > stock_disponible:
                return JsonResponse({
                    'success': False,
                    'message': f'Stock insuficiente. Disponible: {stock_disponible}, solicitado: {cantidad_total}'
                }, status=400)
            
            # Verificar si el producto ya está en el carrito
            if item_existente:
                # Actualizar cantidad del item existente
                item_existente.cantidad = cantidad_total
                item_existente.save()
                mensaje = f"Se agregaron {cantidad} unidades más de {producto.nombre}"
            else:
                # Crear nuevo item en el carrito
                ItemCarrito.objects.create(
                    carrito=carrito,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=producto.precio
                )
                mensaje = f"{producto.nombre} agregado al carrito"
            
            # Recargar carrito para obtener total actualizado
            carrito.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'message': mensaje,
                'carrito_id': carrito.id_carrito,
                'total_items': carrito.get_total_items(),
                'total_precio': float(carrito.get_total_precio())
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON inválido'
            }, status=400)
        except Exception as e:
            logger.error(f"Error en CarritoView.post: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al agregar al carrito: {str(e)}'
            }, status=500)

    def put(self, request):
        """Actualizar cantidad de un item en el carrito"""
        try:
            data = json.loads(request.body)
            item_id = data.get('item_id')
            cantidad = data.get('cantidad')
            
            if not item_id or cantidad is None:
                return JsonResponse({
                    'success': False,
                    'message': 'ID de item y cantidad requeridos'
                }, status=400)
            
            try:
                item = ItemCarrito.objects.select_related('producto').get(id_item=item_id)
            except ItemCarrito.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Item no encontrado'
                }, status=404)
            
            if cantidad <= 0:
                # Eliminar el item si la cantidad es 0 o menor
                producto_nombre = item.producto.nombre
                item.delete()
                mensaje = f"{producto_nombre} eliminado del carrito"
            else:
                # Validar stock disponible
                from productos.models import Stock
                stock_obj = Stock.objects.filter(producto=item.producto).first()
                stock_disponible = stock_obj.cantidad if stock_obj else 0
                
                if cantidad > stock_disponible:
                    return JsonResponse({
                        'success': False,
                        'message': f'Stock insuficiente. Disponible: {stock_disponible}, solicitado: {cantidad}'
                    }, status=400)
                
                item.cantidad = cantidad
                item.save()
                mensaje = f"Cantidad de {item.producto.nombre} actualizada"
            
            # Obtener carrito actualizado
            carrito = item.carrito
            carrito.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'message': mensaje,
                'total_items': carrito.get_total_items(),
                'total_precio': float(carrito.get_total_precio())
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON inválido'
            }, status=400)
        except Exception as e:
            logger.error(f"Error en CarritoView.put: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al actualizar carrito: {str(e)}'
            }, status=500)

    def delete(self, request):
        """Eliminar item del carrito"""
        try:
            item_id = request.GET.get('item_id')
            
            if not item_id:
                return JsonResponse({
                    'success': False,
                    'message': 'ID de item requerido'
                }, status=400)
            
            try:
                item = ItemCarrito.objects.select_related('producto', 'carrito').get(id_item=item_id)
                producto_nombre = item.producto.nombre
                carrito = item.carrito
                item.delete()
                
                # Recargar carrito para obtener total actualizado
                carrito.refresh_from_db()
                
                return JsonResponse({
                    'success': True,
                    'message': f"{producto_nombre} eliminado del carrito",
                    'total_items': carrito.get_total_items(),
                    'total_precio': float(carrito.get_total_precio())
                }, status=200)
                
            except ItemCarrito.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Item no encontrado'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error en CarritoView.delete: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error al eliminar del carrito: {str(e)}'
            }, status=500)

    def _get_or_create_carrito(self, request):
        """Obtener o crear carrito para el usuario/sesión"""
        # Si el usuario está autenticado (usando sesión personalizada), usar su carrito
        if request.session.get('is_authenticated'):
            try:
                from autenticacion_usuarios.models import Cliente, Usuario
                user_id = request.session.get('user_id')
                if user_id:
                    usuario = Usuario.objects.get(id=user_id)
                    # Verificar si es cliente
                    if usuario.id_rol.nombre.lower() == 'cliente':
                        try:
                            cliente = Cliente.objects.get(id=usuario)
                            carrito, created = Carrito.objects.get_or_create(
                                cliente=cliente,
                                activo=True,
                                defaults={'session_key': None}
                            )
                            return carrito
                        except Cliente.DoesNotExist:
                            pass
            except Exception:
                pass
        
        # Si no está autenticado o no es cliente, usar session_key
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        carrito, created = Carrito.objects.get_or_create(
            session_key=session_key,
            activo=True,
            defaults={'cliente': None}
        )
        return carrito


@method_decorator(csrf_exempt, name='dispatch')
class CarritoManagementView(View):
    """CU9: Gestión avanzada del carrito"""
    
    def post(self, request):
        """CU9: Operaciones avanzadas del carrito"""
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            if action == 'clear':
                return self._clear_carrito(request)
            elif action == 'merge':
                return self._merge_carritos(request, data)
            elif action == 'save_for_later':
                return self._save_for_later(request, data)
            elif action == 'apply_discount':
                return self._apply_discount(request, data)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Acción no válida'
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON inválido'
            }, status=400)
        except Exception as e:
            logger.error(f"Error en CarritoManagementView.post: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error en gestión del carrito: {str(e)}'
            }, status=500)

    def _clear_carrito(self, request):
        """CU9: Limpiar completamente el carrito"""
        carrito = self._get_or_create_carrito(request)
        ItemCarrito.objects.filter(carrito=carrito).delete()
        carrito.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'message': 'Carrito limpiado exitosamente',
            'total_items': carrito.get_total_items(),
            'total_precio': float(carrito.get_total_precio())
        }, status=200)

    def _merge_carritos(self, request, data):
        """CU9: Fusionar carritos (útil cuando un visitante se registra)"""
        carrito_origen_id = data.get('carrito_origen_id')
        
        if not carrito_origen_id:
            return JsonResponse({
                'success': False,
                'message': 'ID de carrito origen requerido'
            }, status=400)
        
        try:
            carrito_origen = Carrito.objects.get(id_carrito=carrito_origen_id)
            carrito_destino = self._get_or_create_carrito(request)
            
            # Mover items del carrito origen al destino
            items_origen = ItemCarrito.objects.filter(carrito=carrito_origen)
            items_movidos = 0
            
            for item in items_origen:
                # Verificar si el producto ya existe en el carrito destino
                item_existente = ItemCarrito.objects.filter(
                    carrito=carrito_destino,
                    producto=item.producto
                ).first()
                
                if item_existente:
                    # Sumar cantidades
                    item_existente.cantidad += item.cantidad
                    item_existente.save()
                else:
                    # Crear nuevo item
                    ItemCarrito.objects.create(
                        carrito=carrito_destino,
                        producto=item.producto,
                        cantidad=item.cantidad,
                        precio_unitario=item.precio_unitario
                    )
                items_movidos += 1
            
            # Eliminar carrito origen
            carrito_origen.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Carrito fusionado exitosamente. {items_movidos} items movidos.',
                'carrito_id': carrito_destino.id_carrito
            }, status=200)
            
        except Carrito.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Carrito origen no encontrado'
            }, status=404)

    def _save_for_later(self, request, data):
        """CU9: Guardar item para más tarde (marcar como favorito)"""
        item_id = data.get('item_id')
        
        if not item_id:
            return JsonResponse({
                'success': False,
                'message': 'ID de item requerido'
            }, status=400)
        
        try:
            item = ItemCarrito.objects.get(id_item=item_id)
            # Por ahora solo eliminamos del carrito, en el futuro se podría guardar en una tabla de favoritos
            producto_nombre = item.producto.nombre
            item.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'{producto_nombre} guardado para más tarde'
            }, status=200)
            
        except ItemCarrito.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Item no encontrado'
            }, status=404)

    def _apply_discount(self, request, data):
        """CU9: Aplicar descuento al carrito usando cupones reales"""
        codigo_descuento = data.get('codigo_descuento')
        porcentaje = data.get('porcentaje', 0)
        
        if not codigo_descuento and not porcentaje:
            return JsonResponse({
                'success': False,
                'message': 'Código de descuento o porcentaje requerido'
            }, status=400)
        
        carrito = self._get_or_create_carrito(request)
        
        # Validar cupón desde la base de datos
        if codigo_descuento:
            try:
                from productos.models import CuponDescuento
                from django.utils import timezone
                from decimal import Decimal
                
                cupon = CuponDescuento.objects.get(codigo=codigo_descuento.upper().strip())
                ahora = timezone.now()
                
                # Validar que esté activo
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
                
                # Calcular total del carrito
                items = ItemCarrito.objects.filter(carrito=carrito)
                total_carrito = sum(item.get_subtotal() for item in items)
                
                # Validar monto mínimo
                if cupon.monto_minimo > 0 and total_carrito < float(cupon.monto_minimo):
                    return JsonResponse({
                        'success': False,
                        'message': f'El cupón requiere un monto mínimo de Bs. {cupon.monto_minimo:.2f}'
                    }, status=400)
                
                # Aplicar descuento según tipo
                items_actualizados = 0
                if cupon.tipo_descuento == 'porcentaje':
                    porcentaje = float(cupon.valor_descuento)
                    for item in items:
                        precio_original = float(item.producto.precio)
                        precio_descuento = precio_original * (1 - porcentaje / 100)
                        item.precio_unitario = Decimal(str(precio_descuento))
                        item.save()
                        items_actualizados += 1
                else:  # fijo (monto fijo)
                    # Aplicar descuento fijo al total (distribuido proporcionalmente)
                    descuento_total = float(cupon.valor_descuento)
                    if descuento_total > total_carrito:
                        descuento_total = total_carrito
                    
                    # Distribuir el descuento proporcionalmente
                    for item in items:
                        subtotal = float(item.get_subtotal())
                        proporcion = subtotal / total_carrito if total_carrito > 0 else 0
                        descuento_item = descuento_total * proporcion
                        precio_original = float(item.producto.precio)
                        precio_descuento = precio_original - (descuento_item / item.cantidad)
                        if precio_descuento < 0:
                            precio_descuento = 0
                        item.precio_unitario = Decimal(str(precio_descuento))
                        item.save()
                        items_actualizados += 1
                
                # Incrementar usos del cupón
                cupon.usos_actuales += 1
                cupon.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Cupón "{cupon.codigo}" aplicado exitosamente',
                    'descuento_aplicado': porcentaje if cupon.tipo_descuento == 'porcentaje' else descuento_total,
                    'tipo_descuento': cupon.tipo_descuento,
                    'items_actualizados': items_actualizados
                }, status=200)
                
            except CuponDescuento.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Código de descuento no válido'
                }, status=404)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error aplicando cupón: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'message': f'Error al aplicar cupón: {str(e)}'
                }, status=500)
        
        # Si se proporciona porcentaje directo (sin código)
        if porcentaje:
            items = ItemCarrito.objects.filter(carrito=carrito)
            items_actualizados = 0
            
            for item in items:
                precio_original = float(item.producto.precio)
                precio_descuento = precio_original * (1 - porcentaje / 100)
                item.precio_unitario = Decimal(str(precio_descuento))
                item.save()
                items_actualizados += 1
            
            return JsonResponse({
                'success': True,
                'message': f'Descuento del {porcentaje}% aplicado a {items_actualizados} items',
                'descuento_aplicado': porcentaje
            }, status=200)

    def _get_or_create_carrito(self, request):
        """Método auxiliar para obtener o crear carrito"""
        # Si el usuario está autenticado (usando sesión personalizada), usar su carrito
        if request.session.get('is_authenticated'):
            try:
                from autenticacion_usuarios.models import Cliente, Usuario
                user_id = request.session.get('user_id')
                if user_id:
                    usuario = Usuario.objects.get(id=user_id)
                    # Verificar si es cliente
                    if usuario.id_rol.nombre.lower() == 'cliente':
                        try:
                            cliente = Cliente.objects.get(id=usuario)
                            carrito, created = Carrito.objects.get_or_create(
                                cliente=cliente,
                                activo=True,
                                defaults={'session_key': None}
                            )
                            return carrito
                        except Cliente.DoesNotExist:
                            pass
            except Exception:
                pass
        
        # Si no está autenticado o no es cliente, usar session_key
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        carrito, created = Carrito.objects.get_or_create(
            session_key=session_key,
            activo=True,
            defaults={'cliente': None}
        )
        return carrito