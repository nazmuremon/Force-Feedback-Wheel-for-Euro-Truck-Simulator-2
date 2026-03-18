#ifndef __USBD_EP_CONF_H
#define __USBD_EP_CONF_H

#ifdef USBCON

#include <stdint.h>

#include "usbd_def.h"

typedef struct {
  uint32_t ep_adress;
  uint32_t ep_size;
#if defined(USB)
  uint32_t ep_kind;
#endif
} ep_desc_t;

#define DEV_NUM_EP 0x03U

#if defined(USB)
#define PMA_EP0_OUT_ADDR (8U * DEV_NUM_EP)
#define PMA_EP0_IN_ADDR (PMA_EP0_OUT_ADDR + USB_MAX_EP0_SIZE)
#define PMA_CUSTOM_HID_OUT_ADDR (PMA_EP0_IN_ADDR + USB_MAX_EP0_SIZE)
#define PMA_CUSTOM_HID_IN_ADDR (PMA_CUSTOM_HID_OUT_ADDR + CUSTOM_HID_EPOUT_SIZE)
#endif

extern const ep_desc_t ep_def[DEV_NUM_EP + 1U];

#endif  // USBCON
#endif  // __USBD_EP_CONF_H
