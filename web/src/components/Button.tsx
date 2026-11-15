import type { ButtonHTMLAttributes } from 'react';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'ghost';
  size?: 'md' | 'lg';
};

export function Button({ variant = 'default', size = 'md', className, type, ...rest }: Props) {
  const cls = ['btn', variant === 'default' ? '' : variant, size === 'lg' ? 'lg' : '', className]
    .filter(Boolean)
    .join(' ');
  return <button type={type ?? 'button'} className={cls} {...rest} />;
}
