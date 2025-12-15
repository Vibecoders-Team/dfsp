import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import path from 'path';
const OUT_DIR = process.env.VITE_OUT_DIR || 'build';
export default defineConfig({
    server: {
        port: 5173,
        host: true,
    },
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    worker: {
        format: 'es',
    },
    build: {
        target: 'esnext',
        outDir: OUT_DIR,
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (!id)
                        return undefined;
                    if (id.includes('node_modules')) {
                        if (id.includes('@walletconnect/core'))
                            return 'vendor-wc-core';
                        if (id.includes('@walletconnect/universal-provider'))
                            return 'vendor-wc-universal';
                        if (id.includes('@reown/'))
                            return 'vendor-reown';
                        if (id.includes('/viem/'))
                            return 'vendor-viem';
                        if (id.includes('/abitype/'))
                            return 'vendor-abitype';
                        if (id.includes('/react/') || id.includes('/react-dom/'))
                            return 'vendor-react';
                        if (id.includes('ethers'))
                            return 'vendor-ethers';
                        if (id.includes('@walletconnect') || id.includes('walletconnect'))
                            return 'vendor-walletconnect';
                        if (id.includes('w3m-modal') || id.includes('web3modal'))
                            return 'vendor-w3m-modal';
                        if (id.includes('ox'))
                            return 'vendor-ox';
                        if (id.includes('zod'))
                            return 'vendor-zod';
                        if (id.includes('vaul'))
                            return 'vendor-vaul';
                        if (id.includes('recharts'))
                            return 'vendor-recharts';
                        if (id.includes('react-virtuoso'))
                            return 'vendor-virtuoso';
                        return 'vendor';
                    }
                }
            }
        },
        ...(process.env.ANALYZE === '1' ? {
            rollupOptions: {
                plugins: [
                    visualizer({ filename: path.resolve(OUT_DIR, 'stats.html'), title: 'DFSP bundle analysis', gzipSize: true })
                ]
            }
        } : {})
    },
});
