// SPDX-License-Identifier: GPL-2.0+
/* Fine3399 160x80 ST7735S framebuffer driver with its 24-row GRAM offset. */

#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <video/mipi_display.h>

#include "fbtft.h"

#define DRVNAME "fb_fine3399_st7735s"
#define Y_OFFSET 24

#define DEFAULT_GAMMA \
	"0F 1A 0F 18 2F 28 20 22 1F 1B 23 37 00 07 02 10\n" \
	"0F 1B 0F 17 33 2C 29 2E 30 30 39 3F 00 07 03 10"

static const s16 default_init_sequence[] = {
	-1, MIPI_DCS_SOFT_RESET,
	-2, 150,
	-1, MIPI_DCS_EXIT_SLEEP_MODE,
	-2, 500,
	-1, 0xB1, 0x01, 0x2C, 0x2D,
	-1, 0xB2, 0x01, 0x2C, 0x2D,
	-1, 0xB3, 0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D,
	-1, 0xB4, 0x07,
	-1, 0xC0, 0xA2, 0x02, 0x84,
	-1, 0xC1, 0xC5,
	-1, 0xC2, 0x0A, 0x00,
	-1, 0xC3, 0x8A, 0x2A,
	-1, 0xC4, 0x8A, 0xEE,
	-1, 0xC5, 0x0E,
	-1, MIPI_DCS_EXIT_INVERT_MODE,
	-1, MIPI_DCS_SET_PIXEL_FORMAT, MIPI_DCS_PIXEL_FMT_16BIT,
	-1, MIPI_DCS_SET_DISPLAY_ON,
	-2, 100,
	-1, MIPI_DCS_ENTER_NORMAL_MODE,
	-2, 10,
	-3,
};

static void set_addr_win(struct fbtft_par *par, int xs, int ys, int xe, int ye)
{
	ys += Y_OFFSET;
	ye += Y_OFFSET;
	write_reg(par, MIPI_DCS_SET_COLUMN_ADDRESS,
		  xs >> 8, xs & 0xff, xe >> 8, xe & 0xff);
	write_reg(par, MIPI_DCS_SET_PAGE_ADDRESS,
		  ys >> 8, ys & 0xff, ye >> 8, ye & 0xff);
	write_reg(par, MIPI_DCS_WRITE_MEMORY_START);
}

#define MY BIT(7)
#define MX BIT(6)
#define MV BIT(5)

static int set_var(struct fbtft_par *par)
{
	switch (par->info->var.rotate) {
	case 0:
		write_reg(par, MIPI_DCS_SET_ADDRESS_MODE,
			  MX | MY | (par->bgr << 3));
		break;
	case 270:
		write_reg(par, MIPI_DCS_SET_ADDRESS_MODE,
			  MY | MV | (par->bgr << 3));
		break;
	case 180:
		write_reg(par, MIPI_DCS_SET_ADDRESS_MODE, par->bgr << 3);
		break;
	case 90:
		write_reg(par, MIPI_DCS_SET_ADDRESS_MODE,
			  MX | MV | (par->bgr << 3));
		break;
	}
	return 0;
}

#define CURVE(num, idx) curves[(num) * par->gamma.num_values + (idx)]
static int set_gamma(struct fbtft_par *par, u32 *curves)
{
	int i;
	int j;

	for (i = 0; i < par->gamma.num_curves; i++)
		for (j = 0; j < par->gamma.num_values; j++)
			CURVE(i, j) &= 0x3f;
	for (i = 0; i < par->gamma.num_curves; i++)
		write_reg(par, 0xE0 + i,
			  CURVE(i, 0), CURVE(i, 1), CURVE(i, 2), CURVE(i, 3),
			  CURVE(i, 4), CURVE(i, 5), CURVE(i, 6), CURVE(i, 7),
			  CURVE(i, 8), CURVE(i, 9), CURVE(i, 10), CURVE(i, 11),
			  CURVE(i, 12), CURVE(i, 13), CURVE(i, 14), CURVE(i, 15));
	return 0;
}
#undef CURVE

static struct fbtft_display display = {
	.regwidth = 8,
	.width = 80,
	.height = 160,
	.init_sequence = default_init_sequence,
	.gamma_num = 2,
	.gamma_len = 16,
	.gamma = DEFAULT_GAMMA,
	.fbtftops = {
		.set_addr_win = set_addr_win,
		.set_var = set_var,
		.set_gamma = set_gamma,
	},
};

FBTFT_REGISTER_DRIVER(DRVNAME, "fine3399,st7735s", &display);

MODULE_ALIAS("spi:" DRVNAME);
MODULE_ALIAS("spi:fine3399-st7735s");
MODULE_DESCRIPTION("Fine3399 ST7735S 160x80 framebuffer driver");
MODULE_AUTHOR("Fine3399 firmware project");
MODULE_LICENSE("GPL");
