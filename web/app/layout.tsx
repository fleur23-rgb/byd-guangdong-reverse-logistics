import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '全国动力电池逆向物流网络决策模型',
  description: '面向中国任意地区的退役动力电池逆向物流参数化测算工具，内置广东论文参考案例。',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
