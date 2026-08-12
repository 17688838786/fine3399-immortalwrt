#define _GNU_SOURCE

#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/if.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define WIDTH 160
#define HEIGHT 80
#define PIXELS (WIDTH * HEIGHT)
#define FRAME_BYTES (PIXELS * 2)
#define PACK_HEADER_BYTES 16

#define RGB(r, g, b) ((uint16_t)((((r) & 0xf8) << 8) | (((g) & 0xfc) << 3) | ((b) >> 3)))

static const uint16_t C_PANEL = RGB(43, 38, 91);
static const uint16_t C_BORDER = RGB(153, 140, 207);
static const uint16_t C_TEXT = RGB(248, 244, 255);
static const uint16_t C_MUTED = RGB(174, 168, 200);
static const uint16_t C_OK = RGB(78, 226, 148);
static const uint16_t C_WARN = RGB(255, 207, 105);
static const uint16_t C_ERROR = RGB(255, 105, 135);
static const uint16_t C_DOWN = RGB(108, 215, 255);
static const uint16_t C_UP = RGB(255, 164, 218);
static const uint16_t C_CPU = RGB(103, 204, 244);
static const uint16_t C_RAM = RGB(177, 148, 238);
static const uint16_t C_DISK = RGB(255, 169, 213);

struct animation {
	void *mapping;
	size_t size;
	const uint8_t *frames;
	unsigned count;
	unsigned delay_ms;
};

struct metrics {
	char iface[IFNAMSIZ];
	int online;
	double rx_rate;
	double tx_rate;
	int cpu;
	int memory;
	int storage;
	int temperature;
	int service[4];
	char docker_count[16];
};

static double monotonic_seconds(void)
{
	struct timespec value;
	clock_gettime(CLOCK_MONOTONIC, &value);
	return value.tv_sec + value.tv_nsec / 1000000000.0;
}

static double env_number(const char *name, double fallback, double minimum)
{
	const char *text = getenv(name);
	char *end = NULL;
	double value;
	if (!text || !*text)
		return fallback;
	value = strtod(text, &end);
	return end != text && value >= minimum ? value : fallback;
}

static uint16_t blend(uint16_t background, uint16_t foreground)
{
	unsigned br = (background >> 11) & 31, bg = (background >> 5) & 63, bb = background & 31;
	unsigned fr = (foreground >> 11) & 31, fg = (foreground >> 5) & 63, fb = foreground & 31;
	return (uint16_t)((((br + fr * 3) / 4) << 11) | (((bg + fg * 3) / 4) << 5) | ((bb + fb * 3) / 4));
}

static void pixel(uint16_t *canvas, int x, int y, uint16_t color)
{
	if ((unsigned)x < WIDTH && (unsigned)y < HEIGHT)
		canvas[y * WIDTH + x] = color;
}

static void rectangle(uint16_t *canvas, int x, int y, int width, int height, uint16_t color)
{
	int row, column;
	for (row = 0; row < height; row++)
		for (column = 0; column < width; column++)
			pixel(canvas, x + column, y + row, color);
}

static void panel(uint16_t *canvas)
{
	int x, y;
	for (y = 10; y < 70; y++)
		for (x = 5; x < 72; x++)
			canvas[y * WIDTH + x] = blend(canvas[y * WIDTH + x], C_PANEL);
	for (x = 8; x < 69; x++) {
		pixel(canvas, x, 10, C_BORDER);
		pixel(canvas, x, 69, C_BORDER);
	}
	for (y = 13; y < 67; y++) {
		pixel(canvas, 5, y, C_BORDER);
		pixel(canvas, 71, y, C_BORDER);
	}
}

static const uint8_t *glyph(char c)
{
	static const uint8_t blank[5] = {0};
	static const uint8_t table[][6] = {
		{'0', 0x3e,0x51,0x49,0x45,0x3e}, {'1',0x00,0x42,0x7f,0x40,0x00},
		{'2',0x42,0x61,0x51,0x49,0x46}, {'3',0x21,0x41,0x45,0x4b,0x31},
		{'4',0x18,0x14,0x12,0x7f,0x10}, {'5',0x27,0x45,0x45,0x45,0x39},
		{'6',0x3c,0x4a,0x49,0x49,0x30}, {'7',0x01,0x71,0x09,0x05,0x03},
		{'8',0x36,0x49,0x49,0x49,0x36}, {'9',0x06,0x49,0x49,0x29,0x1e},
		{'A',0x7e,0x11,0x11,0x11,0x7e}, {'B',0x7f,0x49,0x49,0x49,0x36},
		{'C',0x3e,0x41,0x41,0x41,0x22}, {'D',0x7f,0x41,0x41,0x22,0x1c},
		{'E',0x7f,0x49,0x49,0x49,0x41}, {'F',0x7f,0x09,0x09,0x09,0x01},
		{'G',0x3e,0x41,0x49,0x49,0x7a}, {'H',0x7f,0x08,0x08,0x08,0x7f},
		{'I',0x00,0x41,0x7f,0x41,0x00}, {'J',0x20,0x40,0x41,0x3f,0x01},
		{'K',0x7f,0x08,0x14,0x22,0x41}, {'L',0x7f,0x40,0x40,0x40,0x40},
		{'M',0x7f,0x02,0x0c,0x02,0x7f}, {'N',0x7f,0x04,0x08,0x10,0x7f},
		{'O',0x3e,0x41,0x41,0x41,0x3e}, {'P',0x7f,0x09,0x09,0x09,0x06},
		{'Q',0x3e,0x41,0x51,0x21,0x5e}, {'R',0x7f,0x09,0x19,0x29,0x46},
		{'S',0x46,0x49,0x49,0x49,0x31}, {'T',0x01,0x01,0x7f,0x01,0x01},
		{'U',0x3f,0x40,0x40,0x40,0x3f}, {'V',0x1f,0x20,0x40,0x20,0x1f},
		{'W',0x3f,0x40,0x38,0x40,0x3f}, {'X',0x63,0x14,0x08,0x14,0x63},
		{'Y',0x07,0x08,0x70,0x08,0x07}, {'Z',0x61,0x51,0x49,0x45,0x43},
		{'%',0x23,0x13,0x08,0x64,0x62}, {'/',0x20,0x10,0x08,0x04,0x02},
		{'.',0x00,0x60,0x60,0x00,0x00}, {'-',0x08,0x08,0x08,0x08,0x08},
		{':',0x00,0x36,0x36,0x00,0x00}, {'?',0x02,0x01,0x51,0x09,0x06},
	};
	size_t i;
	for (i = 0; i < sizeof(table) / sizeof(table[0]); i++)
		if (table[i][0] == (uint8_t)c)
			return &table[i][1];
	return blank;
}

static int text_width(const char *text, int scale)
{
	return text && *text ? (int)strlen(text) * 6 * scale - scale : 0;
}

static void text(uint16_t *canvas, int x, int y, const char *value, int scale, uint16_t color)
{
	int column, row, dx, dy;
	for (; *value; value++, x += 6 * scale) {
		const uint8_t *bits = glyph(*value);
		for (column = 0; column < 5; column++)
			for (row = 0; row < 7; row++)
				if (bits[column] & (1u << row))
					for (dy = 0; dy < scale; dy++)
						for (dx = 0; dx < scale; dx++)
							pixel(canvas, x + column * scale + dx, y + row * scale + dy, color);
	}
}

static void text_right(uint16_t *canvas, int right, int y, const char *value, int scale, uint16_t color)
{
	text(canvas, right - text_width(value, scale) + 1, y, value, scale, color);
}

static void dot(uint16_t *canvas, int x, int y, uint16_t color)
{
	rectangle(canvas, x + 1, y, 4, 6, color);
	rectangle(canvas, x, y + 1, 6, 4, color);
}

static void docker_icon(uint16_t *canvas, int x, int y, uint16_t color)
{
	int item;
	const uint8_t boxes[][2] = {{0,1},{1,1},{2,1},{1,0}};
	for (item = 0; item < 4; item++)
		rectangle(canvas, x + boxes[item][0] * 4, y + boxes[item][1] * 3, 3, 3, color);
	rectangle(canvas, x - 1, y + 7, 14, 2, color);
	pixel(canvas, x + 13, y + 6, color);
	pixel(canvas, x + 14, y + 6, color);
	pixel(canvas, x + 15, y + 5, C_TEXT);
}

static int load_raw(const char *path, uint16_t *output)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	ssize_t offset = 0, count;
	if (fd < 0)
		return -1;
	while (offset < FRAME_BYTES && (count = read(fd, (uint8_t *)output + offset, FRAME_BYTES - offset)) > 0)
		offset += count;
	close(fd);
	return offset == FRAME_BYTES ? 0 : -1;
}

static int load_background(const char *theme, uint16_t *output)
{
	char path[512];
	if (theme && *theme) {
		snprintf(path, sizeof(path), "%s/status.rgb565", theme);
		if (!load_raw(path, output))
			return 0;
	}
	return load_raw("/usr/share/fine3399-lcd/status.rgb565", output);
}

static uint16_t le16(const uint8_t *value)
{
	return (uint16_t)(value[0] | (value[1] << 8));
}

static int load_animation_file(const char *path, struct animation *animation)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	struct stat info;
	const uint8_t *bytes;
	size_t expected;
	if (fd < 0 || fstat(fd, &info) || info.st_size < PACK_HEADER_BYTES) {
		if (fd >= 0) close(fd);
		return -1;
	}
	animation->mapping = mmap(NULL, info.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
	close(fd);
	if (animation->mapping == MAP_FAILED)
		return -1;
	bytes = animation->mapping;
	animation->size = info.st_size;
	animation->count = le16(bytes + 12);
	animation->delay_ms = le16(bytes + 14);
	expected = PACK_HEADER_BYTES + (size_t)animation->count * FRAME_BYTES;
	if (memcmp(bytes, "F339LCD1", 8) || le16(bytes + 8) != WIDTH || le16(bytes + 10) != HEIGHT ||
		!animation->count || animation->delay_ms < 50 || expected != animation->size) {
		munmap(animation->mapping, animation->size);
		memset(animation, 0, sizeof(*animation));
		return -1;
	}
	animation->frames = bytes + PACK_HEADER_BYTES;
	return 0;
}

static int load_animation(const char *theme, const char *name, struct animation *animation)
{
	char path[512];
	if (theme && *theme) {
		snprintf(path, sizeof(path), "%s/%s", theme, name);
		if (!load_animation_file(path, animation))
			return 0;
	}
	snprintf(path, sizeof(path), "/usr/share/fine3399-lcd/%s", name);
	return load_animation_file(path, animation);
}

static void default_interface(char output[IFNAMSIZ])
{
	FILE *file = fopen("/proc/net/route", "r");
	char line[256], iface[IFNAMSIZ], destination[32];
	strcpy(output, "br-lan");
	if (!file) return;
	fgets(line, sizeof(line), file);
	while (fgets(line, sizeof(line), file))
		if (sscanf(line, "%15s %31s", iface, destination) == 2 && !strcmp(destination, "00000000")) {
			strncpy(output, iface, IFNAMSIZ - 1);
			output[IFNAMSIZ - 1] = '\0';
			break;
		}
	fclose(file);
}

static int interface_online(const char *iface)
{
	int fd = socket(AF_INET, SOCK_DGRAM, 0), result = 0;
	struct ifreq request = {0};
	if (fd < 0) return 0;
	strncpy(request.ifr_name, iface, IFNAMSIZ - 1);
	result = ioctl(fd, SIOCGIFADDR, &request) == 0 && strcmp(iface, "br-lan");
	close(fd);
	return result;
}

static uint64_t counter(const char *iface, const char *name)
{
	char path[256];
	unsigned long long value = 0;
	FILE *file;
	snprintf(path, sizeof(path), "/sys/class/net/%s/statistics/%s_bytes", iface, name);
	file = fopen(path, "r");
	if (file) { fscanf(file, "%llu", &value); fclose(file); }
	return value;
}

static void cpu_sample(uint64_t *total, uint64_t *idle)
{
	FILE *file = fopen("/proc/stat", "r");
	unsigned long long value[8] = {0};
	int i;
	*total = *idle = 0;
	if (!file) return;
	fscanf(file, "cpu %llu %llu %llu %llu %llu %llu %llu %llu",
		&value[0],&value[1],&value[2],&value[3],&value[4],&value[5],&value[6],&value[7]);
	fclose(file);
	for (i = 0; i < 8; i++) *total += value[i];
	*idle = value[3] + value[4];
}

static int memory_percent(void)
{
	FILE *file = fopen("/proc/meminfo", "r");
	char key[64], unit[16];
	unsigned long long value, total = 0, available = 0;
	if (!file) return 0;
	while (fscanf(file, "%63s %llu %15s", key, &value, unit) == 3) {
		if (!strcmp(key, "MemTotal:")) total = value;
		else if (!strcmp(key, "MemAvailable:")) available = value;
	}
	fclose(file);
	return total ? (int)((total - available) * 100 / total) : 0;
}

static int storage_percent(void)
{
	FILE *file = fopen("/proc/mounts", "r");
	char device[256], mountpoint[256], type[64], options[256];
	int dump, pass, best = 0, priority = -1;
	struct statvfs stat;
	if (!file) return 0;
	while (fscanf(file, "%255s %255s %63s %255s %d %d", device, mountpoint, type, options, &dump, &pass) == 6) {
		int candidate = !strncmp(device, "/dev/nvme", 9) ? 2 : (strstr(mountpoint, "p4") || strstr(mountpoint, "share")) ? 1 : 0;
		if (candidate > priority && !statvfs(mountpoint, &stat) && stat.f_blocks) {
			best = (int)((stat.f_blocks - stat.f_bavail) * 100 / stat.f_blocks);
			priority = candidate;
		}
	}
	fclose(file);
	return best;
}

static int temperature(void)
{
	DIR *directory = opendir("/sys/class/thermal");
	struct dirent *entry;
	char path[256];
	long value;
	FILE *file;
	if (!directory) return -1;
	while ((entry = readdir(directory))) {
		if (strncmp(entry->d_name, "thermal_zone", 12)) continue;
		snprintf(path, sizeof(path), "/sys/class/thermal/%s/temp", entry->d_name);
		file = fopen(path, "r");
		if (file && fscanf(file, "%ld", &value) == 1 && value > 0 && value < 150000) {
			fclose(file); closedir(directory); return (int)((value + 500) / 1000);
		}
		if (file) fclose(file);
	}
	closedir(directory);
	return -1;
}

static int command_status(const char *path, const char *argument)
{
	pid_t child;
	int status, nullfd;
	if (access(path, X_OK)) return 0;
	child = fork();
	if (!child) {
		nullfd = open("/dev/null", O_RDWR);
		if (nullfd >= 0) { dup2(nullfd, STDOUT_FILENO); dup2(nullfd, STDERR_FILENO); close(nullfd); }
		execl(path, path, argument, (char *)NULL);
		_exit(127);
	}
	if (child < 0 || waitpid(child, &status, 0) < 0) return 0;
	return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static int line_count(const char *command)
{
	FILE *pipe = popen(command, "r");
	char line[128];
	int count = 0;
	if (!pipe) return 0;
	while (fgets(line, sizeof(line), pipe)) count++;
	pclose(pipe);
	return count;
}

static void services(struct metrics *metrics)
{
	static const char *paths[] = {"/etc/init.d/openclash", "/etc/init.d/ddns-go", "/etc/init.d/frps", "/etc/init.d/dockerd"};
	int i, running, total;
	for (i = 0; i < 4; i++) metrics->service[i] = command_status(paths[i], "running");
	if (!metrics->service[3]) strcpy(metrics->docker_count, "OFF");
	else {
		running = line_count("docker ps -q 2>/dev/null");
		total = line_count("docker ps -aq 2>/dev/null");
		snprintf(metrics->docker_count, sizeof(metrics->docker_count), "%d/%d", running, total);
		if (running != total) metrics->service[3] = -1;
	}
}

static void rate_text(double value, char output[16])
{
	const char units[] = "BKMG";
	int unit = 0;
	while (value >= 1024 && unit < 3) { value /= 1024; unit++; }
	if (unit >= 2 && value < 100) snprintf(output, 16, "%.1f%c", value, units[unit]);
	else snprintf(output, 16, "%.0f%c", value, units[unit]);
}

static void progress(uint16_t *canvas, int y, const char *label, int value, uint16_t color)
{
	char percentage[8];
	if (value < 0)
		value = 0;
	if (value > 100)
		value = 100;
	text(canvas, 10, y - 6, label, 1, C_TEXT);
	rectangle(canvas, 31, y, 18, 4, RGB(80, 69, 126));
	rectangle(canvas, 31, y, (18 * value) / 100, 4, color);
	snprintf(percentage, sizeof(percentage), "%d%%", value);
	text_right(canvas, 68, y - 6, percentage, 1, C_TEXT);
}

static void render_network(uint16_t *canvas, const uint16_t *background, const struct metrics *metrics)
{
	char down[20], up[20], value[16];
	memcpy(canvas, background, FRAME_BYTES); panel(canvas);
	dot(canvas, 11, 17, metrics->online ? C_OK : C_ERROR);
	text(canvas, 21, 15, metrics->online ? "ONLINE" : "OFFLINE", 1, metrics->online ? C_OK : C_ERROR);
	rate_text(metrics->rx_rate, value); snprintf(down, sizeof(down), "D %s", value);
	rate_text(metrics->tx_rate, value); snprintf(up, sizeof(up), "U %s", value);
	text(canvas, 10, 32, down, text_width(down, 2) <= 58 ? 2 : 1, C_DOWN);
	text(canvas, 10, 51, up, text_width(up, 2) <= 58 ? 2 : 1, C_UP);
}

static void render_system(uint16_t *canvas, const uint16_t *background, const struct metrics *metrics)
{
	char value[12];
	uint16_t temp_color = metrics->temperature >= 80 ? C_ERROR : metrics->temperature >= 65 ? C_WARN : C_TEXT;
	memcpy(canvas, background, FRAME_BYTES); panel(canvas);
	if (metrics->temperature < 0) strcpy(value, "--C"); else snprintf(value, sizeof(value), "%dC", metrics->temperature);
	text(canvas, 10, 13, value, 2, temp_color);
	progress(canvas, 36, "CPU", metrics->cpu, C_CPU);
	progress(canvas, 50, "RAM", metrics->memory, C_RAM);
	progress(canvas, 64, "SSD", metrics->storage, C_DISK);
}

static void render_services(uint16_t *canvas, const uint16_t *background, const struct metrics *metrics)
{
	static const char *names[] = {"CLASH", "DDNS", "FRPS"};
	static const int rows[] = {29, 41, 53, 65};
	int i;
	memcpy(canvas, background, FRAME_BYTES); panel(canvas);
	text(canvas, 10, 13, "SERVICES", 1, C_TEXT);
	for (i = 0; i < 4; i++) {
		uint16_t color = metrics->service[i] > 0 ? C_OK : metrics->service[i] < 0 ? C_ERROR : C_MUTED;
		dot(canvas, 10, rows[i] - 1, color);
		if (i < 3) text(canvas, 19, rows[i] - 4, names[i], 1, C_TEXT);
		else { docker_icon(canvas, 20, rows[i] - 5, C_DOWN); text_right(canvas, 68, rows[i] - 4, metrics->docker_count, 1, color); }
	}
}

static void play_animation(uint16_t *framebuffer, const struct animation *animation, double seconds)
{
	double start = monotonic_seconds();
	unsigned index = 0;
	if (!animation->frames || seconds <= 0) return;
	while (monotonic_seconds() - start < seconds) {
		memcpy(framebuffer, animation->frames + (size_t)index * FRAME_BYTES, FRAME_BYTES);
		index = (index + 1) % animation->count;
		usleep(animation->delay_ms * 1000);
	}
}

static void release_animation(struct animation *animation)
{
	if (animation->mapping && animation->mapping != MAP_FAILED)
		munmap(animation->mapping, animation->size);
	memset(animation, 0, sizeof(*animation));
}

static void blend_frames(
	uint16_t *output,
	const uint16_t *from,
	const uint16_t *to,
	unsigned amount
)
{
	unsigned index;
	for (index = 0; index < PIXELS; index++) {
		unsigned source = from[index], target = to[index];
		unsigned source_r = (source >> 11) & 31, source_g = (source >> 5) & 63, source_b = source & 31;
		unsigned target_r = (target >> 11) & 31, target_g = (target >> 5) & 63, target_b = target & 31;
		unsigned red = (source_r * (255 - amount) + target_r * amount + 127) / 255;
		unsigned green = (source_g * (255 - amount) + target_g * amount + 127) / 255;
		unsigned blue = (source_b * (255 - amount) + target_b * amount + 127) / 255;
		output[index] = (uint16_t)((red << 11) | (green << 5) | blue);
	}
}

static void play_transition(
	uint16_t *framebuffer,
	uint16_t *scratch,
	const uint16_t *current,
	const uint16_t *next,
	const struct animation *animation,
	double fade_seconds
)
{
	unsigned index, fade_frames;
	if (!animation->frames)
		return;
	fade_frames = (unsigned)(fade_seconds * 1000 / animation->delay_ms + 0.5);
	if (fade_frames < 1)
		fade_frames = 1;
	if (fade_frames * 2 > animation->count)
		fade_frames = animation->count / 2;
	for (index = 0; index < animation->count; index++) {
		const uint16_t *frame = (const uint16_t *)(animation->frames + (size_t)index * FRAME_BYTES);
		if (index < fade_frames) {
			unsigned amount = ((index + 1) * 255) / fade_frames;
			blend_frames(scratch, current, frame, amount);
			memcpy(framebuffer, scratch, FRAME_BYTES);
		} else if (index >= animation->count - fade_frames) {
			unsigned amount = ((index - (animation->count - fade_frames) + 1) * 255) / fade_frames;
			blend_frames(scratch, frame, next, amount);
			memcpy(framebuffer, scratch, FRAME_BYTES);
		} else {
			memcpy(framebuffer, frame, FRAME_BYTES);
		}
		usleep(animation->delay_ms * 1000);
	}
}

int main(void)
{
	const char *fb_path = getenv("FINE3399_LCD_FB");
	const char *theme = getenv("FINE3399_LCD_THEME_DIR");
	double page_seconds = env_number("FINE3399_LCD_PAGE_SECONDS", 8, 1);
	double service_seconds = env_number("FINE3399_LCD_SERVICE_SECONDS", 5, 1);
	double startup_seconds = env_number("FINE3399_LCD_STARTUP_SECONDS", 6, 0);
	double transition_seconds = env_number("FINE3399_LCD_TRANSITION_SECONDS", 0.6, 0);
	unsigned animation_every = (unsigned)env_number("FINE3399_LCD_ANIMATION_EVERY", 3, 1);
	uint16_t *background = malloc(FRAME_BYTES), *canvas = malloc(FRAME_BYTES);
	uint16_t *next_canvas = malloc(FRAME_BYTES), *scratch = malloc(FRAME_BYTES), *framebuffer;
	struct animation startup = {0}, animation = {0};
	struct metrics metrics = {0};
	uint64_t old_rx = 0, old_tx = 0, old_total = 0, old_idle = 0;
	double previous = monotonic_seconds(), services_at = 0;
	unsigned rounds = 0;
	int fb, page = 0;
	if (!fb_path || !background || !canvas || !next_canvas || !scratch || load_background(theme, background)) return 1;
	load_animation(theme, "startup.rgb565", &startup);
	load_animation(theme, "animation.rgb565", &animation);
	fb = open(fb_path, O_RDWR | O_CLOEXEC);
	if (fb < 0) return 1;
	framebuffer = mmap(NULL, FRAME_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0);
	if (framebuffer == MAP_FAILED) return 1;
	play_animation(framebuffer, &startup, startup_seconds);
	release_animation(&startup);
	default_interface(metrics.iface);
	old_rx = counter(metrics.iface, "rx"); old_tx = counter(metrics.iface, "tx"); cpu_sample(&old_total, &old_idle);
	for (;;) {
		double now = monotonic_seconds(), elapsed = now - previous, duration;
		char current[IFNAMSIZ];
		uint64_t rx, tx, total, idle, delta_total, delta_idle;
		default_interface(current);
		if (strcmp(current, metrics.iface)) { strcpy(metrics.iface, current); old_rx = counter(current, "rx"); old_tx = counter(current, "tx"); }
		rx = counter(metrics.iface, "rx"); tx = counter(metrics.iface, "tx"); cpu_sample(&total, &idle);
		delta_total = total - old_total; delta_idle = idle - old_idle;
		metrics.rx_rate = elapsed > 0 ? (rx - old_rx) / elapsed : 0;
		metrics.tx_rate = elapsed > 0 ? (tx - old_tx) / elapsed : 0;
		metrics.cpu = delta_total ? (int)((delta_total - delta_idle) * 100 / delta_total) : 0;
		metrics.online = interface_online(metrics.iface); metrics.memory = memory_percent(); metrics.storage = storage_percent(); metrics.temperature = temperature();
		old_rx = rx; old_tx = tx; old_total = total; old_idle = idle; previous = now;
		if (now - services_at >= 10) { services(&metrics); services_at = now; }
		if (page == 0) { render_network(canvas, background, &metrics); duration = page_seconds; }
		else if (page == 1) { render_system(canvas, background, &metrics); duration = page_seconds; }
		else { render_services(canvas, background, &metrics); duration = service_seconds; }
		memcpy(framebuffer, canvas, FRAME_BYTES);
		for (int tick = 0; tick < (int)(duration * 2); tick++) usleep(500000);
		page++;
		if (page == 3) {
			rounds++;
			if (animation.frames && rounds % animation_every == 0) {
				render_network(next_canvas, background, &metrics);
				play_transition(framebuffer, scratch, canvas, next_canvas, &animation, transition_seconds);
			}
			page = 0;
			previous = monotonic_seconds();
			old_rx = counter(metrics.iface, "rx");
			old_tx = counter(metrics.iface, "tx");
			cpu_sample(&old_total, &old_idle);
		}
	}
}
