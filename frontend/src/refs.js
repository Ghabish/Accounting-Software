// Reference data loaders shared by pickers (cached per session).
import { api } from './api.js'
import { lookups } from './store.js'

const all = async (path, params = {}) => (await api.get(path, { page_size: 500, ...params })).items
export const refs = {
  accounts: () => lookups.get('accounts', () => api.get('/accounts', { postable: true, active: true })),
  allAccounts: () => lookups.get('allAccounts', () => api.get('/accounts')),
  sites: () => lookups.get('sites', () => all('/sites', { active: true })),
  costCentres: () => lookups.get('ccs', () => all('/cost-centres', { active: true })),
  suppliers: () => lookups.get('suppliers', () => all('/ap/suppliers', { active: true })),
  customers: () => lookups.get('customers', () => all('/ar/customers', { active: true })),
  employees: () => lookups.get('employees', () => all('/employees', { active: true })),
  bankAccounts: () => lookups.get('banks', () => all('/banking/accounts', { active: true })),
  taxCodes: () => lookups.get('taxCodes', () => all('/tax/codes', { active: true })),
  dimTypes: () => lookups.get('dimTypes', () => all('/dimension-types')),
  dimValues: () => lookups.get('dimValues', () => all('/dimension-values', { active: true })),
  periods: () => lookups.get('periods', () => api.get('/periods')),
  fiscalYears: () => lookups.get('fys', () => api.get('/fiscal-years')),
  supplierCategories: () => lookups.get('supCats', () => api.get('/ap/supplier-categories')),
  customerCategories: () => lookups.get('cusCats', () => api.get('/ar/customer-categories')),
  assetCategories: () => lookups.get('assetCats', () => api.get('/assets/categories')),
  paymentMethods: () => lookups.get('pms', () => all('/cinema/payment-methods')),
  roles: () => lookups.get('roles', () => api.get('/admin/roles')),
}
export const opt = {
  account: (a) => ({ value: a.id, label: `${a.code} ${a.name}`, raw: a }),
  coded: (x) => ({ value: x.id, label: `${x.code} ${x.name || x.title || ''}`.trim(), raw: x }),
}
