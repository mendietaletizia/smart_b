"""
Vistas para integración con Stripe Payment Intents (pago en la misma página)
Permite crear Payment Intents y confirmar pagos desde el frontend usando Stripe Elements
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.db import transaction
from django.utils import timezone
import json
import logging
from decimal import Decimal

# Import opcional de stripe
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None
    STRIPE_AVAILABLE = False

from .models import Venta, PagoOnline, MetodoPago, Carrito, ItemCarrito, DetalleVenta, Comprobante
from autenticacion_usuarios.models import Usuario, Cliente, Bitacora
from productos.models import Stock
from .comprobantes_views import ComprobanteView

logger = logging.getLogger(__name__)

# Configurar Stripe con la clave secreta desde variables de entorno
if STRIPE_AVAILABLE:
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
else:
    logger.warning("Stripe no está instalado. Las funcionalidades de pago con Stripe no estarán disponibles.")


def _get_client_ip(request):
    """Obtener IP del cliente"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@method_decorator(csrf_exempt, name='dispatch')
class GetStripePublishableKeyView(View):
    """
    Obtiene la clave pública de Stripe para el frontend
    GET /api/ventas/stripe/publishable-key/
    """
    
    def get(self, request):
        if not STRIPE_AVAILABLE:
            return JsonResponse({
                'success': False,
                'message': 'Stripe no está disponible. Por favor, instale el módulo stripe.'
            }, status=503)
        
        publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', '')
        return JsonResponse({
            'success': True,
            'publishable_key': publishable_key
        })


@method_decorator(csrf_exempt, name='dispatch')
class CreatePaymentIntentView(View):
    """
    Crea un PaymentIntent de Stripe para una venta.
    POST /api/ventas/stripe/create-payment-intent/
    
    Requiere:
    - direccion_entrega: Dirección de entrega
    - notas: Notas adicionales (opcional)
    
    Retorna:
    - client_secret: Secreto del cliente del PaymentIntent
    - payment_intent_id: ID del PaymentIntent
    - pago_id: ID del registro de PagoOnline
    - venta_id: ID de la venta creada
    """
    
    def post(self, request):
        if not STRIPE_AVAILABLE:
            return JsonResponse({
                'success': False,
                'message': 'Stripe no está disponible. Por favor, instale el módulo stripe.'
            }, status=503)
        
        try:
            # Verificar autenticación
            if not request.session.get('is_authenticated'):
                return JsonResponse({
                    'success': False,
                    'message': 'Debe iniciar sesión para realizar pagos'
                }, status=401)
            
            # Obtener datos del request
            data = json.loads(request.body)
            direccion_entrega = data.get('direccion_entrega', '')
            notas = data.get('notas', '')
            
            # Validaciones básicas
            if not direccion_entrega.strip():
                return JsonResponse({
                    'success': False,
                    'message': 'La dirección de entrega es obligatoria'
                }, status=400)
            
            # Obtener cliente autenticado
            user_id = request.session.get('user_id')
            try:
                usuario = Usuario.objects.get(id=user_id)
                cliente = Cliente.objects.get(id=usuario)
            except (Usuario.DoesNotExist, Cliente.DoesNotExist):
                return JsonResponse({
                    'success': False,
                    'message': 'Cliente no encontrado'
                }, status=404)
            
            # Obtener carrito del cliente
            try:
                carrito = Carrito.objects.get(cliente=cliente, activo=True)
                items_carrito = ItemCarrito.objects.filter(carrito=carrito)
                
                if not items_carrito.exists():
                    return JsonResponse({
                        'success': False,
                        'message': 'El carrito está vacío'
                    }, status=400)
            except Carrito.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'No hay productos en el carrito'
                }, status=400)
            
            # Calcular total
            total = sum(item.get_subtotal() for item in items_carrito)
            
            if total <= 0:
                return JsonResponse({
                    'success': False,
                    'message': 'El total debe ser mayor a 0'
                }, status=400)
            
            # Verificar stock antes de crear la venta
            productos_sin_stock = []
            for item in items_carrito.select_related('producto'):
                stock_obj = Stock.objects.filter(producto=item.producto).first()
                stock_disponible = stock_obj.cantidad if stock_obj else 0
                
                if stock_disponible < item.cantidad:
                    productos_sin_stock.append({
                        'producto': item.producto.nombre,
                        'solicitado': item.cantidad,
                        'disponible': stock_disponible
                    })
            
            if productos_sin_stock:
                mensaje = 'Stock insuficiente para los siguientes productos: '
                mensaje += ', '.join([f"{p['producto']} (solicitado: {p['solicitado']}, disponible: {p['disponible']})" 
                                    for p in productos_sin_stock])
                return JsonResponse({
                    'success': False,
                    'message': mensaje
                }, status=400)
            
            # Crear venta y detalles en una transacción
            with transaction.atomic():
                venta = Venta.objects.create(
                    cliente=cliente,
                    total=total,
                    estado='pendiente',
                    metodo_pago='stripe',
                    direccion_entrega=direccion_entrega,
                    notas=notas
                )
                
                # Crear detalles de venta
                for item in items_carrito.select_related('producto'):
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=item.producto,
                        cantidad=item.cantidad,
                        precio_unitario=item.precio_unitario
                    )
            
            # Notificar a administradores sobre nueva venta
            try:
                from autenticacion_usuarios.notificaciones_views import notificar_nueva_venta
                notificar_nueva_venta(venta)
            except Exception as e:
                logger.warning(f"Error notificando nueva venta: {str(e)}")
            
            # Obtener o crear método de pago Stripe
            metodo_pago, _ = MetodoPago.objects.get_or_create(nombre='Stripe')
            
            # Convertir monto a centavos (Stripe usa USD para tarjetas de prueba)
            # Para proyecto universitario, usamos USD
            amount_cents = int(float(total) * 100)
            
            # Crear Payment Intent en Stripe
            try:
                payment_intent = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency='usd',  # USD para compatibilidad con tarjetas de prueba
                    payment_method_types=['card'],  # Solo tarjetas de crédito/débito (sin Amazon Pay, Link, Cash App Pay)
                    metadata={
                        'venta_id': str(venta.id_venta),
                        'cliente_id': str(cliente.id.id),
                    },
                    description=f'Pago Venta #{venta.id_venta} - SmartSales365'
                )
            except stripe.error.StripeError as e:
                logger.error(f"Error de Stripe al crear Payment Intent: {str(e)}")
                # Revertir la venta creada
                venta.delete()
                return JsonResponse({
                    'success': False,
                    'message': f'Error al crear sesión de pago: {str(e)}'
                }, status=400)
            
            # Crear registro de PagoOnline
            pago_online = PagoOnline.objects.create(
                venta=venta,
                monto=total,
                estado='pendiente',
                metodo_pago=metodo_pago,
                stripe_payment_intent_id=payment_intent.id,
                referencia=f"STRIPE-{timezone.now().strftime('%Y%m%d')}-{payment_intent.id[:8]}"
            )
            
            # Registrar en bitácora
            try:
                Bitacora.objects.create(
                    id_usuario=usuario,
                    accion='STRIPE_PAYMENT_INTENT_CREATED',
                    modulo='VENTAS',
                    descripcion=f'Payment Intent creado para venta #{venta.id_venta}',
                    ip=_get_client_ip(request)
                )
            except Exception as e:
                logger.warning(f"Error al registrar en bitácora: {str(e)}")
            
            logger.info(f"✅ Payment Intent {payment_intent.id} creado para Venta #{venta.id_venta}")
            
            return JsonResponse({
                'success': True,
                'client_secret': payment_intent.client_secret,
                'payment_intent_id': payment_intent.id,
                'pago_id': pago_online.id_pago,
                'venta_id': venta.id_venta,
                'monto': float(total)
            }, status=201)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Formato de datos inválido'
            }, status=400)
        except Exception as e:
            logger.error(f"Error en CreatePaymentIntentView: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error interno: {str(e)}'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class VerifyPaymentIntentView(View):
    """
    Verifica el estado de un PaymentIntent y actualiza el registro de PagoOnline.
    POST /api/ventas/stripe/verify-payment-intent/
    
    Requiere:
    - payment_intent_id: ID del PaymentIntent de Stripe
    
    Retorna:
    - status: Estado del PaymentIntent
    - pago_online_id: ID del registro de PagoOnline
    - venta_id: ID de la venta
    """
    
    def post(self, request):
        if not STRIPE_AVAILABLE:
            return JsonResponse({
                'success': False,
                'message': 'Stripe no está disponible. Por favor, instale el módulo stripe.'
            }, status=503)
        
        try:
            data = json.loads(request.body)
            payment_intent_id = data.get('payment_intent_id')
            
            if not payment_intent_id:
                return JsonResponse({
                    'success': False,
                    'message': 'payment_intent_id es requerido'
                }, status=400)
            
            # Recuperar Payment Intent de Stripe
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            except stripe.error.StripeError as e:
                logger.error(f"Error de Stripe al recuperar Payment Intent: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error al verificar pago: {str(e)}'
                }, status=400)
            
            status_pi = payment_intent.status
            logger.info(f"🔍 Verificando Payment Intent: {payment_intent_id}, Estado: {status_pi}")
            
            # Buscar el pago por Payment Intent ID
            try:
                pago_online = PagoOnline.objects.get(stripe_payment_intent_id=payment_intent_id)
            except PagoOnline.DoesNotExist:
                logger.error(f"❌ No se encontró el PagoOnline con Payment Intent: {payment_intent_id}")
                return JsonResponse({
                    'success': False,
                    'message': 'Pago no encontrado en la base de datos',
                    'payment_intent_id': payment_intent_id
                }, status=404)
            
            venta = pago_online.venta
            
            # Si el pago fue exitoso en Stripe, actualizar el registro
            if status_pi == 'succeeded':
                comprobante_data = None
                
                with transaction.atomic():
                    pago_online.estado = 'exitoso'
                    pago_online.save(update_fields=['estado'])
                    
                    # Actualizar estado de la venta
                    venta.estado = 'completada'
                    venta.metodo_pago = 'stripe'
                    venta.save(update_fields=['estado', 'metodo_pago'])
                    
                    # Actualizar stock
                    for detalle in venta.detalles.all():
                        stock_obj = Stock.objects.filter(producto=detalle.producto).first()
                        if stock_obj:
                            stock_obj.cantidad -= detalle.cantidad
                            if stock_obj.cantidad < 0:
                                stock_obj.cantidad = 0
                            stock_obj.save()
                    
                    # Limpiar carrito
                    try:
                        carrito = Carrito.objects.get(cliente=venta.cliente, activo=True)
                        carrito.items.all().delete()
                        carrito.delete()
                    except Carrito.DoesNotExist:
                        pass
                
                # CU12: Generar comprobante automáticamente después de pago exitoso
                try:
                    comprobante_view = ComprobanteView()
                    # Verificar si ya existe comprobante
                    if hasattr(venta, 'comprobante'):
                        comprobante = venta.comprobante
                        # Regenerar PDF si ya existe
                        try:
                            pdf_path = comprobante_view._generar_pdf(comprobante, venta)
                            comprobante.pdf_ruta = pdf_path
                            comprobante.save()
                        except Exception as e:
                            logger.warning(f"Error al regenerar PDF del comprobante: {str(e)}")
                    else:
                        # Crear nuevo comprobante
                        comprobante = comprobante_view._generar_comprobante(venta, 'factura')
                    
                    comprobante_data = {
                        'id': comprobante.id_comprobante,
                        'numero': comprobante.nro,
                        'tipo': comprobante.tipo,
                        'fecha': comprobante.fecha_emision.isoformat(),
                        'pdf_url': f'/api/ventas/comprobantes/{venta.id_venta}/pdf/'
                    }
                    logger.info(f"✅ Comprobante #{comprobante.nro} generado automáticamente para venta #{venta.id_venta}")
                except Exception as e:
                    logger.error(f"Error al generar comprobante automático: {str(e)}", exc_info=True)
                    # No fallar la venta si el comprobante falla, pero registrar el error
                
                # Registrar en bitácora
                try:
                    user_id = request.session.get('user_id')
                    if user_id:
                        usuario = Usuario.objects.get(id=user_id)
                        Bitacora.objects.create(
                            id_usuario=usuario,
                            accion='STRIPE_PAYMENT_SUCCEEDED',
                            modulo='VENTAS',
                            descripcion=f'Pago Stripe exitoso para venta #{venta.id_venta}',
                            ip=_get_client_ip(request)
                        )
                except Exception as e:
                    logger.warning(f"Error al registrar en bitácora: {str(e)}")
                
                logger.info(f"✅ PagoOnline #{pago_online.id_pago} y Venta #{venta.id_venta} confirmados exitosamente")
                
                response_data = {
                    'success': True,
                    'status': status_pi,
                    'pago_online_id': pago_online.id_pago,
                    'venta_id': venta.id_venta,
                    'message': 'Pago confirmado exitosamente'
                }
                
                # Agregar información del comprobante si se generó exitosamente
                if comprobante_data:
                    response_data['comprobante'] = comprobante_data
                
                return JsonResponse(response_data, status=200)
            
            # Si el pago requiere acción adicional
            elif status_pi in ['requires_payment_method', 'requires_confirmation', 'requires_action']:
                pago_online.estado = 'pendiente'
                pago_online.save(update_fields=['estado'])
                
                return JsonResponse({
                    'success': False,
                    'status': status_pi,
                    'pago_online_id': pago_online.id_pago,
                    'venta_id': venta.id_venta,
                    'message': f'Pago en estado: {status_pi}. Requiere acción adicional.'
                }, status=200)
            
            # Si el pago falló
            else:
                pago_online.estado = 'fallido'
                pago_online.save(update_fields=['estado'])
                
                return JsonResponse({
                    'success': False,
                    'status': status_pi,
                    'pago_online_id': pago_online.id_pago,
                    'venta_id': venta.id_venta,
                    'message': f'Pago fallido o en estado inesperado: {status_pi}'
                }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Formato de datos inválido'
            }, status=400)
        except Exception as e:
            logger.error(f"Error en VerifyPaymentIntentView: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Error interno: {str(e)}'
            }, status=500)
